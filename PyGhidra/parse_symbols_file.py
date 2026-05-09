from ghidra.app.script import GhidraScript
from ghidra.program.model.address import Address, AddressFactory
from ghidra.program.model.mem import MemoryBlock
from ghidra.program.model.symbol import SourceType, SymbolType

import string

def parse_assignment(line):
	line = line.strip()
	if len(line) == 0:
		return None

	# comments
	if line.startswith('//'):
		return None
	if line.startswith('/*'):
		return None

	# parse
	parts = line.split('=')
	var_name = parts[0].strip()
	semicolon = parts[1].index(';')
	value_str = parts[1][:semicolon].strip()
	
	# lines may include MATH
	if '-' in value_str or '+' in value_str:
		parts = value_str.split('-') if '-' in value_str else value_str.split('+')
		base_value = int(parts[0].strip(), 16)
		operand = int(parts[1].strip())
		# and some of that is just +1 meant to indicate THUMB, but Ghidra will fail with that
		value_int = (base_value + operand) & ~1
		value_str = hex(value_int)

	return (var_name, value_str)

class SymbolParser:
	addr_factory: AddressFactory
	overlay_blocks: list[MemoryBlock]
	regular_blocks: list[MemoryBlock]
	current_overlay: int | None
	symbols: dict[str, Address]
	
	def __init__(self, script: GhidraScript, path: str):
		currentProgram = script.getCurrentProgram()
		self.addr_factory = currentProgram.getAddressFactory()
		memory = currentProgram.getMemory()
		
		self.overlay_blocks = []
		self.regular_blocks = []
		for block in memory.getBlocks():
			if block.isOverlay():
				self.overlay_blocks.append(block)
			else:
				self.regular_blocks.append(block)
				
		self.current_overlay: int | None
		
		self.symbols = self.parse(path)
		
	def parse(self, path: str):
		symbols_from_file: dict[str, Address] = {}
		with open(path, 'r') as fs:
			while line := fs.readline():
				if line.startswith('/*'):
					if 'arm9_ov' in line:
						index = line.index('arm9_ov')
						ov_str = line[index+7:]
						ov_str_len = 1
						while len(ov_str) > ov_str_len and ov_str[ov_str_len].isdigit():
							ov_str_len += 1
						ov_str = ov_str[:ov_str_len]
						self.current_overlay = int(ov_str)
					elif 'arm9' in line:
						self.current_overlay = None
			
				tup = parse_assignment(line)
				if tup is None:
					continue

				(name, address) = tup
				if not address.startswith('0x'):
					symbols_from_file[name] = symbols_from_file[address]
				else:
					symbols_from_file[name] = self.resolve_address(address)
		return symbols_from_file

	def resolve_address(self, addr_str: str) -> Address:
		matches = []
		if self.current_overlay is None:
			for block in self.regular_blocks:
				bname = block.getName()
				test_address = self.addr_factory.getAddress(addr_str)
				if test_address is not None and block.contains(test_address):
					matches.append(test_address)
		else:
			overlay_str = f'_{self.current_overlay}'
			for block in self.overlay_blocks:
				bname = block.getName()
				if overlay_str not in bname:
					continue
				
				test_address = self.addr_factory.getAddress(f'{bname}:{addr_str}')
				if test_address is not None and block.contains(test_address):
					matches.append(test_address)
				
		if len(matches) != 1:
			matches_str = [str(m) for m in matches]
			raise Exception(f'Failed to resolve address {addr_str} in overlay {self.current_overlay}. {len(matches)}: {str.join(', ', matches_str)}')
		return matches[0]

def parse_symbols(script: GhidraScript, path: str) -> dict[str, Address]:
	parser = SymbolParser(script, path)
	return parser.symbols
