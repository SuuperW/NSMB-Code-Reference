#@category NDS-SRE
#@runtime PyGhidra

from collections import defaultdict
import os
from pathlib import Path
import sys

from clang.cindex import (
	Cursor,
	Type,
	TypeKind,
)

import header_parser
from importlib import reload
reload(header_parser)

PROJECT_ROOT = os.environ.get('GHIDRA_EXTRACT_SOURCE')
if PROJECT_ROOT is None:
	PROJECT_ROOT = askDirectory('source location', 'load').getAbsolutePath()
assert Path(PROJECT_ROOT).is_dir(), f'The given source directory {PROJECT_ROOT} does not exist. '

nitro_dir = 'nitro_include'
assert Path(f'{PROJECT_ROOT}/{nitro_dir}').exists(), f'The folder "{nitro_dir}" must exist, with the contents of "fake_nitro" copied into it.'
	
os.makedirs(f'{PROJECT_ROOT}/{nitro_dir}/nitro', exist_ok=True)
auto_gen_file = f'{PROJECT_ROOT}/{nitro_dir}/auto-gen.h'
if not Path(auto_gen_file).exists():
	with open(auto_gen_file, 'w') as fs:
		fs.write('#pragma once\n\n')
Path(f'{PROJECT_ROOT}/{nitro_dir}/nitro/cht.h').touch()

types_made: set[str] = set()
wrong_sizes: dict[str, tuple] = {}

def make_fake_nitro_type(name: str):
	# make a file
	file_name = f'{PROJECT_ROOT}/{nitro_dir}/nitro/{name}.h'
	with open(file_name, 'w', newline='') as fs:
		fs.write('#pragma once\n')
		# for now we'll assume all types are at least 4 bytes
		fs.write(f'typedef struct {name} {{ u32 _fake_[1]; }} {name};\n')
	# #include it
	with open(auto_gen_file, 'a', newline='') as fs:
		fs.write(f'#include "nitro/{name}.h"\n')

def record_wrong_size(name: str, expected: int, location: str):
	wrong_sizes[name] = (expected, location)
	
	index = location.rindex(':')
	error_file = location[:index]
	error_line = int(location[index+1:]) - 1
	
	contents: list[str]
	with open(error_file, 'r', newline='') as fs:
		contents = fs.readlines()
	contents[error_line] = '//' + contents[error_line]
	with open(error_file, 'w', newline='') as fs:
		fs.writelines(contents)

def make_fake_macro(name: str):
	with open(auto_gen_file, 'a', newline='') as fs:
		fs.write(f'#define {name} 0\n')

def change_struct_to_typedef(name: str):
	file_name = f'{PROJECT_ROOT}/{nitro_dir}/nitro/{name}.h'
	with open(file_name, 'w', newline='') as fs:
		fs.write('#pragma once\n')
		fs.write(f'typedef int {name};\n')

def add_attr(struct_name: str, attr_name: str):	
	file_name = f'{PROJECT_ROOT}/{nitro_dir}/nitro/{struct_name}.h'
	contents: list[str]
	with open(file_name, 'r', newline='') as fs:
		contents = fs.read()
	if 'union' not in contents:
		contents = contents.replace('u32 _fake_[1];', 'union {\nu32 _fake_[1];\n};\n')
	
	index_struct_close = contents.rindex('}')
	index_union_close = contents[:index_struct_close].rindex('}')
	contents = f'{contents[:index_union_close]}u32 {attr_name};\n{contents[index_union_close:]}'
	
	with open(file_name, 'w', newline='') as fs:
		fs.write(contents)

def get_quoted_name(msg: str) -> tuple[str, str]:
	index = msg.index("'")
	msg = msg[index+1:]
	index = msg.index("'")
	type_name = msg[:index]
	msg = msg[index+1:]
	return type_name, msg

UNKNOWN_TYPE = 'unknown type name'
WRONG_SIZE = "static assertion failed due to requirement 'sizeof("
UNDECLARED_IDENTIFIER = 'use of undeclared identifier'
INVALID_BINARY_OPERANDS = 'invalid operands to binary expression'
NO_MEMBER = 'no member named'

NO_CONVERSION = 'no viable conversion from'
CANNOT_CONVERT = 'cannot convert'

def set_type_size(name: str, size_bytes: int):
	assert (size_bytes & 3) == 0
	
	file_name = f'{PROJECT_ROOT}/{nitro_dir}/nitro/{name}.h'
	contents: str
	with open(file_name, 'r', newline='') as fs:
		contents = fs.read()
	contents = contents.replace('[1]', f'[{size_bytes >> 2}]')
	with open(file_name, 'w', newline='') as fs:
		fs.write(contents)
		
class StructSizeInfo:
	clang_type: Type
	name: str
	expected_size: int
	current_size: int
	assert_location: str
	fields: list[Cursor]
	
	def __init__(self, clang_type, name, expected_size, current_size, assert_location, fields):
		self.clang_type = clang_type
		self.name = name
		self.expected_size = expected_size
		self.current_size = current_size
		self.assert_location = assert_location
		self.fields = fields
	
	def uncomment_assert(self):
		index = self.assert_location.rindex(':')
		error_file = self.assert_location[:index]
		error_line = int(self.assert_location[index+1:]) - 1
		contents: list[str]
		with open(error_file, 'r', newline='') as fs:
			contents = fs.readlines()
		assert contents[error_line].startswith('//')
		contents[error_line] = contents[error_line][2:]
		with open(error_file, 'w', newline='') as fs:
			fs.writelines(contents)

def get_implemented_classes(ci: header_parser.ClassInfo):
	classes = [ci.clang_type]
	for sub in ci.subclasses:
		classes += get_implemented_classes(sub)
	return classes

def collect_errors():
	macros_made: set[str] = set()
	converted_to_typedef: set[str] = set()
	attrs_made: set[str] = set()
	
	max_iterations = 12
	i = 0
	errors = header_parser.parse_project(PROJECT_ROOT, ['-ferror-limit=25'], True)
	while len(errors) != 0 and i < max_iterations:
		unknown_types_this_iteration = 0
		for e in errors:
			if UNKNOWN_TYPE in e:
				index = e.index(UNKNOWN_TYPE)
				type_name = get_quoted_name(e[index+len(UNKNOWN_TYPE):])[0]
				
				if type_name not in types_made:
					make_fake_nitro_type(type_name)
					types_made.add(type_name)
					unknown_types_this_iteration += 1
			elif UNDECLARED_IDENTIFIER in e:
				index = e.index(UNDECLARED_IDENTIFIER)
				identifier = get_quoted_name(e[index+len(UNDECLARED_IDENTIFIER):])[0]
				
				if identifier.isupper():
					# Assume it is a macro for an int
					if identifier not in macros_made:
						make_fake_macro(identifier)
						macros_made.add(identifier)
				else:
					print(e, identifier)
			elif INVALID_BINARY_OPERANDS in e:
				index = e.index(INVALID_BINARY_OPERANDS)
				type_name, msg = get_quoted_name(e[index+len(INVALID_BINARY_OPERANDS):])
				if msg.startswith(' (aka '):
					aka_name, msg = get_quoted_name(msg)
					type_name = get_quoted_name(msg)[0]
				
				if type_name not in converted_to_typedef:
					change_struct_to_typedef(type_name)
					converted_to_typedef.add(type_name)
			elif NO_MEMBER in e:
				index = e.index(NO_MEMBER)
				attr_name, msg = get_quoted_name(e[index+len(NO_MEMBER):])
				type_name = get_quoted_name(msg)[0]
				
				combined = type_name + attr_name
				if combined not in attrs_made:
					add_attr(type_name, attr_name)
					attrs_made.add(combined)
			
			elif NO_CONVERSION in e:
				assert 'int' in e, e
				index = e.index(NO_CONVERSION)
				int_type, msg = get_quoted_name(e[index+len(NO_CONVERSION):])
				type_name = get_quoted_name(msg)[0]

				if type_name not in converted_to_typedef:
					change_struct_to_typedef(type_name)
					converted_to_typedef.add(type_name)
			elif CANNOT_CONVERT in e:
				assert 'int' in e, e
				index = e.index(CANNOT_CONVERT)
				type_name = get_quoted_name(e[index+len(CANNOT_CONVERT):])[0]

				if type_name not in converted_to_typedef:
					change_struct_to_typedef(type_name)
					converted_to_typedef.add(type_name)
		if unknown_types_this_iteration == 0:
			# if a type was unknown, a struct containing it or a pointer to it will be seen with a size as if that field did not exist; this leads to false positives, so we only check this once there are no unknown types found
			for e in errors:
				if WRONG_SIZE in e:
					index = e.index(': error: ')
					location = e[:index]
					index = location.rindex(':')
					location = location[:index]
					
					index = e.index(WRONG_SIZE)
					type_name = e[index+len(WRONG_SIZE):]
					index = type_name.index(')')
					type_name = type_name[:index]

					e = e[-10:-1]
					index = e.index("'")
					expected_size = int(e[index+1:], 16)
					
					record_wrong_size(type_name, expected_size, location)

		errors = header_parser.parse_project(PROJECT_ROOT, ['-ferror-limit=25'], True)
		i += 1
	if len(errors) != 0:
		for e in errors:
			print(e)
		raise Exception(f'reached max iterations, {len(errors)} errors left')
	
def fix_fake_types():
	parse_results = header_parser.parse_project(PROJECT_ROOT, [], False)
		
	wrong_size_types: dict[str, StructSizeInfo] = {}
	types_containing_fake_struct: dict[str, list[str]] = defaultdict(list)
	types_that_were_actually_correct: list[str] = []
	for name in wrong_sizes:
		tup = wrong_sizes[name]
		expected_size = tup[0]
		location = tup[1]
		
		clang_type = parse_results.classes[name].clang_type
		bad_fields: list[Cursor] = []
		for cls in get_implemented_classes(parse_results.classes[name]):
			for field in cls.get_fields():
				if header_parser.unelaborate(field.type).kind in header_parser.pointer_types:
					continue
				fts = header_parser.get_base_type(field.type).spelling
				if fts in types_made:
					bad_fields.append(field)
					types_containing_fake_struct[fts].append(name)
		
		actual_size = clang_type.get_size()
		si = StructSizeInfo(
			clang_type,
			name,
			expected_size,
			clang_type.get_size(),
			location,
			bad_fields)
		if actual_size == expected_size:
			# It got fixed, probably because it was only wrong because of including another wrong type.
			si.uncomment_assert()
			types_that_were_actually_correct.append(name)
		else:
			wrong_size_types[name] = si
			
	for name in types_that_were_actually_correct:
		del wrong_sizes[name]
	
	fake_types_fixed: list[str] = []
	wrong_types_fixed: list[str] = []
	for name in wrong_size_types:
		si = wrong_size_types[name]
		if len(si.fields) != 1:
			continue
		field = si.fields[0]
		fake_type_name = header_parser.get_base_type(field.type).spelling
		if fake_type_name in fake_types_fixed:
			si.uncomment_assert()
			wrong_types_fixed.append(si.name)
			continue
		
		size_diff = si.expected_size - si.current_size
		if field.type.kind == TypeKind.CONSTANTARRAY:
			array_size = field.type.get_array_size()
			size_diff_per_element = size_diff // array_size
			assert size_diff == array_size * size_diff_per_element
			size_diff = size_diff_per_element
		
		set_type_size(fake_type_name, size_diff + 4)
		fake_types_fixed.append(fake_type_name)
		types_made.remove(fake_type_name)
		
		si.uncomment_assert()
		wrong_types_fixed.append(si.name)
		
	for name in wrong_types_fixed:
		del wrong_size_types[name]
		del wrong_sizes[name]
	
if __name__ == "__main__":
	print('finding missing types')
	collect_errors()
	print('finding type sizes')
	while len(wrong_sizes) != 0:
		wrong_sizes_remaining = len(wrong_sizes)
		fix_fake_types()
		if len(wrong_sizes) == wrong_sizes_remaining:
			raise Exception('got stuck, unable to fix types')
