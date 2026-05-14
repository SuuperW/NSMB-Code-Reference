from ghidra.app.script import GhidraScript
from ghidra.program.model.address import Address, AddressFactory
from ghidra.program.model.mem import Memory, MemoryBlock
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
	mem: Memory
	current_overlay: int
	symbols: dict[str, (int, str)] # (overlay_id, hex_address)
	
	def __init__(self, script: GhidraScript, path: str):
		currentProgram = script.getCurrentProgram()
		self.addr_factory = currentProgram.getAddressFactory()
		self.mem = currentProgram.getMemory()
		
		self.current_overlay = -1
		self.symbols = self.parse(path)
		
	def parse(self, path: str):
		symbols_from_file: dict[str, (int, str)] = {}
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
						ov_id = int(ov_str)
						self.current_space = ov_id
					elif 'arm9' in line:
						self.current_space = -1
			
				tup = parse_assignment(line)
				if tup is None:
					continue

				(name, address) = tup
				if not address.startswith('0x'):
					symbols_from_file[name] = symbols_from_file[address]
				else:
					symbols_from_file[name] = (self.current_space, address)
		return symbols_from_file

def parse_symbols(script: GhidraScript, path: str) -> dict[str, Address]:
	parser = SymbolParser(script, path)
	return parser.symbols
