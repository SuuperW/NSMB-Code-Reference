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

class SectionInfo:
	name: str
	address: int
	section_data_size: int
	section_bss_size: int
	is_overlay: bool
	
	end_index: int
	src_index: int | None
	overlay_index: int | None
	
	def __init__(self, table: bytes, table_index: int):
		(nameLen, name) = getString(table, table_index)
		self.name = name
		table_index += nameLen
		self.address = getInt(table, table_index)
		table_index += 4
		self.section_data_size = getInt(table, table_index)
		table_index += 4
		self.section_bss_size = getInt(table, table_index)
		table_index += 4
		self.is_overlay = getBool(table, table_index)
		table_index += 1
		
		self.end_index = table_index
		self.src_index = None
		self.overlay_index = None

class ROM_Importer:
	default_space: AddressSpace
	mem: Memory
	file_contents: bytes
	script: GhidraScript
	program: Program
	
	program_config: dict
	overlay_spaces: dict[int, AddressSpace]
	
	def __init__(self, script: GhidraScript, path: str, name: str, program_config: dict):
		self.program_config = program_config
		self.overlay_spaces = {}
		# Create a new program
		self.script = script
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
				0, self.script.monitor, isOverlay)
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
		self.script.createFunction(
			self.default_space.getAddress(hex(arm7EntryPoint)),
			'entry_arm7')
		
		# create arm9 sections
		currentSectionSrcAddress = arm7DataPointer + arm7Length
		sectionId = 0
		table_index = 0
		overlay_index = 0
		
		section_infos = []
		loaded_overlays = self.program_config.get('loaded_overlays') or []
		extra_ram_spaces = []
		while sectionId < sectionsCount:
			si = SectionInfo(sectionsTable, table_index)
			table_index = si.end_index
			si.src_index = currentSectionSrcAddress
			if si.is_overlay:
				si.overlay_index = overlay_index
				if overlay_index in loaded_overlays:
					extra_ram_spaces.append((si.address, si.address + si.section_bss_size + si.section_bss_size))
				overlay_index += 1
			section_infos.append(si)
			
			# Increment values for next loop
			currentSectionSrcAddress += si.section_data_size
			sectionId += 1
		
		# ram sections
		created_overlays = set()
		for si in section_infos:
			if si.overlay_index is not None:
				if si.overlay_index not in loaded_overlays:
					continue
				else:
					self.overlay_spaces[si.overlay_index] = self.default_space
				created_overlays.add(si.overlay_index)
			
			# Note: space.getAddress(int) does not work! Must use hex str.
			assert si.src_index is not None
			self.createMemoryBlock(
				si.name,
				self.default_space.getAddress(hex(si.address)),
				False,
				si.section_data_size,
				si.section_bss_size,
				importData,
				si.src_index,
			)
		
		# overlays
		groups = self.program_config.get('overlay_groups') or {}
		for group_name in groups:
			space = self.program.createOverlaySpace(group_name, self.default_space)
			for ov_id in groups[group_name]:
				self.overlay_spaces[ov_id] = space
		
		skip_unloaded = self.program_config.get('skip_unloaded_overlays') or False
		for si in section_infos:
			if si.overlay_index is None:
				continue
			if si.overlay_index in created_overlays:
				continue
			if skip_unloaded:
				skip = False
				for ram_range in extra_ram_spaces:
					end = si.address + si.section_data_size + si.section_bss_size
					if end > ram_range[0] and si.address < ram_range[1]:
						skip = True
						break
				if skip:
					continue
			
			# Note: space.getAddress(int) does not work! Must use hex str.
			assert si.src_index is not None
			space: AddressSpace
			if si.overlay_index in self.overlay_spaces:
				space = self.overlay_spaces[si.overlay_index]
			else:
				space = self.program.createOverlaySpace(si.name, self.default_space)
				self.overlay_spaces[si.overlay_index] = space
			self.createMemoryBlock(
				si.name,
				space.getAddress(hex(si.address)),
				si.is_overlay,
				si.section_data_size,
				si.section_bss_size,
				importData,
				si.src_index,
			)
			
		# arm9 entry function
		self.script.createFunction(
			self.default_space.getAddress(hex(arm9EntryPoint)),
			'entry_arm9')

if __name__ == '__main__':
	file_path = askFile('where is ghidraData.bin', 'open').getAbsolutePath()
	importer = ROM_Importer(this, file_path, 'NDS SRE')
	importer.loadRomCode()
