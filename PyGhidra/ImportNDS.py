# Import ROM data. For use with NDS

#@category NDS-SRE
#@runtime PyGhidra

# --- Ghidra classes that we need the names of
from ghidra.app.cmd.disassemble import ArmDisassembleCommand
from ghidra.app.plugin.assembler import (
	Assembler,
	Assemblers,
	AssemblySemanticException,
	AssemblySyntaxException)
from ghidra.app.script import GhidraScript
from ghidra.app.util import MemoryBlockUtils
from ghidra.program.model.address import Address, AddressSet, AddressSpace
from ghidra.program.model.lang import LanguageID
from ghidra.program.model.listing import Program
from ghidra.program.model.mem import Memory, MemoryBlock

# Ghidra shenanigans
def join(ghidra_script: GhidraScript):
	global script
	script = ghidra_script

# Converts a byte array to a 32-bit unsigned int
def getInt(fileBytes: bytes, index: int) -> int:
	# Since we're interfacing with Java, our byte array is stupidly signed.
	# We gotta fix that here.
	intBytes = fileBytes[index:index+4]	
	return intBytes[0] + (intBytes[1] << 8) + (intBytes[2] << 16) + (intBytes[3] << 24)
def getBool(fileBytes, index):
	return False if fileBytes[index] == 0 else True
def getString(fileBytes, index):
	slen = getInt(fileBytes, index)
	index += 4
	intBytes = fileBytes[index:index+slen]
	strBytes = bytearray(intBytes)
	return (slen + 4, strBytes.decode('utf-8'))
# Convert a 32-bit unsigned int to an array of bytes
def getBytes(v):
	intBytes = [v & 0xFF]
	intBytes.append((v >> 8) & 0xFF)
	intBytes.append((v >> 16) & 0xFF)
	intBytes.append((v >> 24) & 0xFF)
	return intBytes

class ROM_Importer:
	default_space: AddressSpace
	mem: Memory
	file_contents: bytes
	program: Program
	
	ram_group: list
	overlay_spaces: dict[int, AddressSpace]
	
	def __init__(self, path: str, name: str, ram_group: list):
		self.ram_group = ram_group
		self.overlay_spaces = {}
		# Create a new program
		self.program = script.createProgram(name, LanguageID('ARM:LE:32:v5t'))
		# get stuff
		self.default_space = self.program.getAddressFactory().getDefaultAddressSpace()
		self.overlay_spaces[-1] = self.default_space
		self.mem = self.program.getMemory()
		with open(path, 'rb') as fs:
			self.file_contents = fs.read()
	
	def createMemoryBlock(self,
	  name: str,
	  address: Address,
	  isOverlay: bool,
	  dataLength: int,
	  bssLength: int,
	  sourceData: bytes,
	  sourceIndex: int
	  ) -> tuple[MemoryBlock | None, MemoryBlock | None]:
		# Create the block(s)
		blockData: MemoryBlock | None = None
		if dataLength != 0:
			blockData = self.mem.createInitializedBlock(
				name, address, dataLength,
				0, script.monitor, isOverlay)
			# Load data into block
			blockData.putBytes(blockData.getStart(), sourceData, sourceIndex, dataLength)
		blockBss: MemoryBlock | None = None
		if bssLength != 0:
			if dataLength != 0:
				name = name + '-bss'
			blockBss = self.mem.createUninitializedBlock(
				name, address.add(dataLength), bssLength, isOverlay)
		
		return blockData, blockBss
	
	def loadRomCode(self):		
		importData: bytes = self.file_contents
		# Read the file's header
		arm9EntryPoint = getInt(importData, 0x00)
		arm9SectoinsPointer = getInt(importData, 0x04)
		arm9SectionsLength = getInt(importData, 0x08)
		sectionsCount = getInt(importData, 0x0C)
		arm7EntryPoint = getInt(importData, 0x10)
		arm7BaseAddress = getInt(importData, 0x14)
		arm7Length = getInt(importData, 0x18)
		arm7DataPointer = 0x1C
		# setup for sectionsTable
		sectionsTable = importData[arm9SectoinsPointer:
			arm9SectoinsPointer+arm9SectionsLength]
		
		# create arm7 section
		arm7Block = self.createMemoryBlock(
			'arm7', self.default_space.getAddress(hex(arm7BaseAddress)), False,
			arm7Length, 0,
			importData, arm7DataPointer
		)[0]
		# arm7 entry function
		script.createFunction(
			self.default_space.getAddress(hex(arm7EntryPoint)),
			'entry_arm7')
		
		# create arm9 sections
		currentSectionSrcAddress = arm7DataPointer + arm7Length
		sectionId = 0
		tableIndex = 0
		overlay_index = 0
		while sectionId < sectionsCount:
			(nameLen, name) = getString(sectionsTable, tableIndex)
			tableIndex += nameLen
			address = getInt(sectionsTable, tableIndex)
			tableIndex += 4
			sectionDataSize = getInt(sectionsTable, tableIndex)
			tableIndex += 4
			sectionBssSize = getInt(sectionsTable, tableIndex)
			tableIndex += 4
			isOverlay = getBool(sectionsTable, tableIndex)
			tableIndex += 1
			
			space = self.default_space
			if isOverlay:
				if overlay_index not in self.ram_group and name not in self.ram_group:
					space = self.program.createOverlaySpace(name, space)
				self.overlay_spaces[overlay_index] = space
				overlay_index += 1
			# Note: space.getAddress(int) does not work! Must use hex str.
			self.createMemoryBlock(
				name, space.getAddress(hex(address)), isOverlay,
				sectionDataSize, sectionBssSize,
				importData, currentSectionSrcAddress,
			)
			
			# Increment values for next loop
			currentSectionSrcAddress += sectionDataSize
			sectionId += 1
		# arm9 entry function
		script.createFunction(
			self.default_space.getAddress(hex(arm9EntryPoint)),
			'entry_arm9')

if __name__ == '__main__':
	global script
	script = this
	
	file_path = askFile('where is ghidraData.bin', 'open').getAbsolutePath()
	importer = ROM_Importer(file_path, 'NDS SRE')
	importer.loadRomCode()
