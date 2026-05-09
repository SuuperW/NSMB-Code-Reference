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
from ghidra.app.util import MemoryBlockUtils
from ghidra.program.model.address import Address, AddressFactory, AddressSet
from ghidra.program.model.lang import LanguageID
from ghidra.program.model.listing import Program
from ghidra.program.model.mem import Memory, MemoryBlock

# --- Python imports. Idk why, but in headless mode we need . in path.
import sys
sys.path.append('.')

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

class Patcher:
	aFactory: AddressFactory
	mem: Memory
	asm: Assembler
	file_contents: bytes
	program: Program
	
	def __init__(self, path: str, createNew = False):
		# Create a new program
		if createNew:
			self.program = createProgram('NDS SRE', LanguageID('ARM:LE:32:v5t'))
		else:
			self.program = currentProgram
		# get stuff
		self.aFactory = self.program.getAddressMap().getAddressFactory()
		self.mem = self.program.getMemory()
		self.asm = Assemblers.getAssembler(self.program)
		# Ghidra headless only works if we start with a program.
		# So the command to run Ghidra creates a program by importing a dummy file.
		# But we don't need or want that memory block.
		if not createNew:
			self.mem.removeBlock(self.mem.getBlocks()[0], monitor);
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
		# Convert address to a Ghidra address obj
		addr_str: str = "0x%08x" % address
		address: Address = self.aFactory.getAddress(addr_str)
		# Create the block(s)
		blockData: MemoryBlock | None = None
		if dataLength != 0:
			blockData = self.mem.createInitializedBlock(
				name, address, dataLength,
				0, monitor, isOverlay)
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
			'arm7', arm7BaseAddress, False,
			arm7Length, 0,
			importData, arm7DataPointer
		)[0]
		# arm7 entry function
		addressInArm7Block = arm7Block.getStart()
		addressInArm7Block.add(arm7EntryPoint - arm7BaseAddress)
		createFunction(addressInArm7Block, "entry_arm7")
		
		# create arm9 sections
		currentSectionSrcAddress = arm7DataPointer + arm7Length
		sectionId = 0
		tableIndex = 0
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

			self.createMemoryBlock(
				name, address, isOverlay,
				sectionDataSize, sectionBssSize,
				importData, currentSectionSrcAddress,
			)

			# Increment values for next loop
			currentSectionSrcAddress += sectionDataSize
			sectionId += 1			
		# arm9 entry function
		createFunction(
			self.aFactory.getAddress(hex(arm9EntryPoint)),
			'entry_arm9')

	def run(self):
		println('Loading data...')
		self.loadRomCode()

dir = ''
if len(getScriptArgs()) == 0:
	dir = askFile('where is ghidraData.bin', 'open').getAbsolutePath()
	patcher = Patcher(dir, True)
	patcher.run()
else:
	# Headless
	dir = getScriptArgs()[0]
	patcher = Patcher(dir)
	patcher.run()
