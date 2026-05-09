# Imports types, methods, and globals from header files using libclang.

#@category NDS-SRE
#@runtime PyGhidra

from importlib import reload
import os
from pathlib import Path
import sys

import parse_symbols_file
import header_parser
reload(parse_symbols_file) # Because re-running a PyGhidra script does not automatically reload imports.
reload(header_parser)
ClassInfo = header_parser.ClassInfo
FunctionInfo = header_parser.FunctionInfo
TypedefInfo = header_parser.TypedefInfo
VarInfo = header_parser.VarInfo
get_friendly_name = header_parser.get_friendly_name
get_base_type = header_parser.get_base_type
clang_pointer_types = header_parser.pointer_types

# curse the ELABORATED!!
def unelaborate(t):
	while t.kind == TypeKind.ELABORATED:
		t = t.get_named_type()
	return t

from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.services import DataTypeManagerService
from ghidra.program.flatapi import FlatProgramAPI
from ghidra.program.model.address import Address, AddressSet
from ghidra.program.model.data import (
	ArrayDataType,
	BuiltInDataType,
	BuiltInDataTypeManager,
	CategoryPath,
	DataType,
	DataTypeConflictHandler,
	FunctionDefinitionDataType,
	EnumDataType,
	PackingType,
	ParameterDefinitionImpl,
	Pointer,
	Structure,
	StructureDataType,
	TypedefDataType,
	Union,
	UnionDataType,
)
from ghidra.program.model.lang import CompilerSpec
from ghidra.program.model.listing import Function, ParameterImpl, VariableStorage
from ghidra.program.model.symbol import Namespace, SourceType

from clang.cindex import Cursor, CursorKind, Type, TypeKind

PROJECT_ROOT = os.environ.get('GHIDRA_EXTRACT_SOURCE')
if PROJECT_ROOT is None:
	PROJECT_ROOT = askDirectory('source location', 'load').getAbsolutePath()
assert Path(PROJECT_ROOT).is_dir(), f'The given source directory {PROJECT_ROOT} does not exist. '

type_manager = currentProgram.getDataTypeManager()
conflictHandler = DataTypeConflictHandler.REPLACE_HANDLER
symbol_table = currentProgram.getSymbolTable()
function_manager = currentProgram.getFunctionManager()
listing = currentProgram.getListing()
flat_api = FlatProgramAPI(currentProgram)

# Ghidra will want to put parameters larger than 4 bytes on the stack, even if r0-r3 haven't been used yet.
# So we gotta fix that.
r0 = currentProgram.getRegister('r0')
r1 = currentProgram.getRegister('r1')
r2 = currentProgram.getRegister('r2')
r3 = currentProgram.getRegister('r3')
param_registers = [r0, r1, r2, r3]
var_storage = {}
for i in range(4):
	# Ghidra won't allow partial register storage, so some of these will be invalid and we won't use them.
	var_storage[i << 8 | 1] = VariableStorage(currentProgram, param_registers[i])
	var_storage[i << 8 | 2] = VariableStorage(currentProgram, *param_registers[i:i+2])
	var_storage[i << 8 | 3] = VariableStorage(currentProgram, *param_registers[i:i+3])
	var_storage[i << 8 | 4] = VariableStorage(currentProgram, *param_registers[i:i+4])

symbols_arm9: dict[str, Address]

nsmb_cr_types_to_ignore = ['BitFlag<u32>', 'BitFlag<u8>', 'StrongBitFlag<u32>']

# doy
dtm_service = state.getTool().getService(DataTypeManagerService)
clibTypeManager = None
for dtm in dtm_service.getDataTypeManagers():
	if dtm.getName() == 'generic_clib':
		clibTypeManager = dtm
		break
assert(clibTypeManager is not None)

ghidra_namespaces: dict[str, Namespace] = {}
def get_namespace_for(name: str, is_class: bool) -> (Namespace, str):
	if '::' not in name:
		return (currentProgram.getGlobalNamespace(), name)
	index = name.rindex('::')
	namespace_full = name[:index]
	label_name = name[index+2:]
	if namespace_full in ghidra_namespaces:
		return (ghidra_namespaces[namespace_full], label_name)
	
	namespace_parent, namespace_last = get_namespace_for(namespace_full, is_class)
	namespace = symbol_table.getNamespace(namespace_last, namespace_parent)
	if namespace is None:
		if is_class:
			namespace = symbol_table.createClass(namespace_parent, namespace_last, SourceType.USER_DEFINED)
		else:
			namespace = symbol_table.createNameSpace(namespace_parent, namespace_last, SourceType.USER_DEFINED)
	
	ghidra_namespaces[namespace_full] = namespace
	return (namespace, label_name)

class UnknownGhidraTypeException(Exception):
	pass
def get_ghidra_type(clang_node: Type, allow_none = False):
	clang_node = unelaborate(clang_node)
	
	type_name = '/' + get_friendly_name(clang_node).replace('::', '/')
	ghidra_type = type_manager.getDataType(type_name)
	if ghidra_type is None:
		if clang_node.kind in clang_pointer_types:
			ptee = clang_node.get_pointee()
			gpt = get_ghidra_type(ptee, allow_none)
			if gpt is not None:
				ghidra_type = type_manager.getPointer(gpt)
			elif allow_none:
				return None
		elif clang_node.kind in (TypeKind.CONSTANTARRAY, TypeKind.INCOMPLETEARRAY):
			atype = clang_node.get_array_element_type()
			# Incomplete arrays report size of -1. Ghidra ... we use a length of 0?
			asize = clang_node.get_array_size() if clang_node.kind == TypeKind.CONSTANTARRAY else 0
			gat = get_ghidra_type(atype, allow_none)
			if gat is not None:
				ghidra_type = ArrayDataType(gat, asize)
			elif allow_none:
				return None
	if ghidra_type is not None:
		type_manager.addDataType(ghidra_type, conflictHandler)
	elif not allow_none:
		raise UnknownGhidraTypeException(f'Cannot get ghidra type {type_name} of kind {clang_node.kind} {clang_node.spelling}')
	return ghidra_type

def create_empty_struct(name: str, union: bool = False):
	space_names = name.split('::')
	cat = CategoryPath('/' + str.join('/', space_names[:-1]))
	name = space_names[-1]
	
	struct: DataType
	if union:
		struct = UnionDataType(cat, name)
	else:
		struct = StructureDataType(cat, name, 0)
	struct.setExplicitPackingValue(4)

	return type_manager.addDataType(struct, conflictHandler)

def create_enum(name: str, clang_node: Type):
	assert(clang_node.kind == TypeKind.ENUM)
	assert(clang_node.get_size() > 0)
	
	space_names = name.split('::')
	cat = CategoryPath('/' + str.join('/', space_names[:-1]))
	name = space_names[-1]

	enum = EnumDataType(cat, name, clang_node.get_size())
	for child in clang_node.get_declaration().get_children():
		if child.kind == CursorKind.ENUM_CONSTANT_DECL:
			enum.add(child.spelling, child.enum_value)
	
	type_manager.addDataType(enum, conflictHandler)

def make_ghidra_function(name: str, clang_func_type: Type, is_thiscall: bool, param_names = None):
	"""
	Makes a Function data type, for the type manager.
	"""
	space_names = name.split('::')
	cat = CategoryPath('/' + str.join('/', space_names[:-1]))
	name = space_names[-1]

	fp_args = []
	i = 0
	for arg in clang_func_type.argument_types():
		fp_args.append(ParameterDefinitionImpl(
			param_names[i] if param_names else None,
			get_ghidra_type(arg),
			None # comment
		))
		i += 1

	func_type = FunctionDefinitionDataType(cat, name)
	func_type.setArguments(*fp_args)
	func_type.setReturnType(get_ghidra_type(clang_func_type.get_result()))
	
	return type_manager.addDataType(func_type, conflictHandler)

def create_function_type(name: str, clang_func_type: Type):
	"""
	Makes a Function data type, for the type manager, and possibly a member pointer struct.
	"""
	if clang_func_type.kind == TypeKind.MEMBERPOINTER:
		class_name = get_friendly_name(clang_func_type.get_class_type())
		clang_func_type = clang_func_type.get_pointee()
		
		func_type = make_ghidra_function(f'{class_name}::{name}_func', clang_func_type, True)
		
		# Struct for the member pointer
		struct = create_empty_struct(name)
		func_ptr = type_manager.getPointer(func_type)
		type_manager.addDataType(func_ptr, conflictHandler)
		struct.add(func_ptr, 0, 'func', None)
		struct.add(clibTypeManager.getDataType('/stddef.h/ptrdiff_t'), 0, 'offset', None)
		return func_type
	else:
		return make_ghidra_function(name, clang_func_type, False)

done_typedefs = set()
def create_typedef(tdef_info: TypedefInfo) -> bool:
	name = tdef_info.new_name
	if name in done_typedefs:
		return True
	
	_func = None
	if tdef_info.old_name == 'code*':
		try:
			_func = create_function_type(name + '_func', get_base_type(tdef_info.renamed_type))
			_func = type_manager.getPointer(_func)
		except UnknownGhidraTypeException:
			return False
	
	space_names = name.split('::')
	cat = CategoryPath('/' + str.join('/', space_names[:-1]))
	name = space_names[-1]
	
	dataType = _func or get_ghidra_type(tdef_info.renamed_type, True)
	if dataType is None:
		if tdef_info.renamed_type.kind == TypeKind.TYPEDEF and tdef_info.old_name not in done_typedefs:
			return False
		else:
			raise Exception(f'Could not get Ghidra type {tdef_info.old_name} for typedef {name}')
	done_typedefs.add(name)
		
	typedef = TypedefDataType(cat, name, dataType)
	type_manager.addDataType(typedef, conflictHandler)
	return True

done_structs = set()
def populate_struct(class_info: ClassInfo):
	clang_type = class_info.clang_type
	assert header_parser.is_class_type(clang_type), clang_type.kind
	
	ghidra_type = type_manager.getDataType('/' + class_info.name.replace('::', '/'))
	assert isinstance(ghidra_type, Structure) or isinstance(ghidra_type, Union)
	
	# Validate that subclasses have been populated first
	for subclass in class_info.subclasses:
		if subclass.name in nsmb_cr_types_to_ignore:
			continue
		if subclass.name not in done_structs:
			return False
	
	sub_vtable_type = None
	sub_vtable_index = 0
	for subclass in class_info.subclasses:
		if subclass.name in nsmb_cr_types_to_ignore:
			continue
		for sub_field in get_ghidra_type(subclass.clang_type).getComponents():
			ghidra_type.add(sub_field.getDataType(), 0, sub_field.getFieldName(), None)
			if sub_vtable_type is None:
				if sub_field.getFieldName() == 'vtable':
					sub_vtable_type = sub_field.getDataType()
					assert isinstance(sub_vtable_type, Pointer)
					sub_vtable_type = sub_vtable_type.getDataType()
				else:
					sub_vtable_index += 1
	
	vtable_methods = class_info.vtable_methods()
	if len(vtable_methods) > 0:
		vtable_type = create_empty_struct(f'{class_info.name}::vtable')
		vtable_ptr_type = type_manager.getPointer(vtable_type)
		vtable_ptr_type = type_manager.addDataType(vtable_ptr_type, conflictHandler)
		if sub_vtable_type is not None:
			# Should it stay where it is, or move to index 0? I don't know of a type in NSMB I can check.
			if sub_vtable_index != 0:
				print(f'Type {class_info.name} has a vtable not at index 0. Check me.')
			vtable_type.replaceWith(sub_vtable_type)
			ghidra_type.replace(sub_vtable_index, vtable_ptr_type, 0, 'vtable', None)
		else:
			ghidra_type.insert(0, vtable_ptr_type, 0, 'vtable', None)
		for method in vtable_methods:
			func_type = type_manager.getDataType('/' + method.name.replace('::', '/'))
			func_ptr_type = type_manager.getPointer(func_type)
			func_ptr_type = type_manager.addDataType(func_ptr_type, conflictHandler)
			vtable_type.add(func_ptr_type, 0, method.name.split('::')[-1], None)
	
	anon_field_count = 0
	padding_count = 0
	for field in clang_type.get_fields():
		field_ghidra_type = None
		ftype = unelaborate(field.type)
		field_name = field.spelling
		
		if field_name in class_info.aligned_fields:
			# We don't know the align value. Assume 4?
			while (ghidra_type.getLength() & 3) != 0 or ghidra_type.getDefinedComponentAtOrAfterOffset(ghidra_type.getLength() - 1) is None:
				ghidra_type.add(type_manager.getDataType('/u8'), 0, f'padding_{padding_count}', None)
				padding_count += 1
		if 'anonymous ' in field_name:
			field_name = f'anon_{anon_field_count}'
			anon_field_count += 1
		if ftype.kind == TypeKind.POINTER and unelaborate(ftype.get_pointee()).kind == TypeKind.FUNCTIONPROTO:
			tname = f'/{class_info.name.replace('::', '/')}/{field_name}_func'
			field_ghidra_type = type_manager.getDataType(tname)
			assert field_ghidra_type is not None, tname
			field_ghidra_type = type_manager.getPointer(field_ghidra_type)
		else:
			field_ghidra_type = get_ghidra_type(ftype)
		
		bits = field.get_bitfield_width()
		if bits == -1:
			ghidra_type.add(field_ghidra_type, 0, field_name, None)
		else:
			ghidra_type.addBitField(field_ghidra_type, bits, field_name, None)
	
	done_structs.add(class_info.name)
	return True

def _create_listing_function(fi: FunctionInfo, address: Address):
	parent_namespace, fname = get_namespace_for(fi.name, fi.class_member)
	
	# Make or get function
	func = function_manager.getFunctionAt(address)
	if func is not None:
		if func.getName() == fname:
			if fi.is_ctor or fi.is_dtor:
				return # expected
			elif func.isThunk():
				pass # expected? but we still need to update it
			else:
				raise Exception(f'??? {fname} {hex(address.getOffset())}')
		func.setName(fname, SourceType.USER_DEFINED)
	else:
		# Ghidra may have auto-generated a symbol that we need to delete
		clear_data = listing.getDataAt(address) is not None
		if clear_data:
			# We don't know how big the function will be! Guess a large value.
			listing.clearCodeUnits(address, address.add(0x4000), False)
		func = flat_api.createFunction(address, fname)
		if func is None:
			raise Exception(f'Could not create function {fname} at {address}')
		# This turns out to be rather complicated. Instead we'll let auto-analyze run after this script.
		#if clear_data:
		#	dc = DisassembleCommand(address, AddressSet(address, address.add(0x4000)), False)
		#	dc.applyTo(currentProgram)
	
	# Set function properties
	if fi.is_thiscall:
		func.setCallingConvention(CompilerSpec.CALLING_CONVENTION_thiscall)
	else:
		func.setCallingConvention(CompilerSpec.CALLING_CONVENTION_default)
	func.setParentNamespace(parent_namespace)
	try:
		func.setReturnType(get_ghidra_type(fi.clang_type.get_result()), SourceType.USER_DEFINED)
	except Exception as e:
		print(f'{fi.name} {hex(address.getOffset())} {get_friendly_name(fi.clang_type.get_result())}')
		raise e

	# Function parameters are hard. Because Ghidra thinks registers should not be used for >4 byte params.
	# And when any params have custom storage, all of them have to.
	func_params = []
	i = 0
	reg_num = 0
	def basic_add_param(pname: str, dt: DataType):
		rcount = ((dt.getLength() + 3) >> 2)
		if reg_num < 4:
			storage = var_storage[reg_num << 8 | rcount]
		else:
			storage = VariableStorage(currentProgram, (reg_num - 4) * 4, dt.getLength())
		func_params.append(ParameterImpl(pname, dt, storage, currentProgram))
		return rcount
	# With custom storage params, we need to expicitly include the this param!
	if fi.is_thiscall:
		owning_type_name = str.join('::', fi.name.split('::')[:-1])
		owning_type = type_manager.getDataType('/' + owning_type_name)
		reg_num += basic_add_param('this', type_manager.getPointer(owning_type))
	for param in fi.clang_type.argument_types():
		param_type = get_ghidra_type(param)
		registers_used = (param_type.getLength() + 3) >> 2
		if reg_num < 4 and registers_used + reg_num > 4:
			# Further, Ghidra won't allow partial register storage. SO WE GOTTA SPLIT IT UP.
			vars_made = 0
			while vars_made < registers_used:
				reg_num += basic_add_param(f'{fi.param_names[i]}_{vars_made}', type_manager.getDataType('/u32'))
				vars_made += 1
		else:
			reg_num += basic_add_param(fi.param_names[i], param_type)
		i += 1
	func.replaceParameters(
		Function.FunctionUpdateType.CUSTOM_STORAGE, # CUSTOM_STORAGE, DYNAMIC_STORAGE_ALL_PARAMS
		True,
		SourceType.USER_DEFINED,
		*func_params)

def create_listing_function(fi: FunctionInfo):
	mangled_names = [fi.mangled_name]
	if fi.is_ctor:
		# We're just going to assume the mangled name doesn't contain extra C1E substrings
		mangled_names.append(fi.mangled_name.replace('C1E', 'C2E'))
		mangled_names.append(fi.mangled_name.replace('C1E', 'C3E'))
		mangled_names.append(fi.mangled_name.replace('C1E', 'CI1E'))
		mangled_names.append(fi.mangled_name.replace('C1E', 'CI2E'))
	elif fi.is_dtor:
		mangled_names.append(fi.mangled_name.replace('D1E', 'D0E'))
		mangled_names.append(fi.mangled_name.replace('D1E', 'D2E'))
	found_any = False
	for mangled_name in mangled_names:
		if mangled_name in symbols_arm9:
			address = symbols_arm9[mangled_name]
			if int(address.getOffset()) == 0x02044B20:
				print(fi.name, fi.mangled_name, hex(int(address.getOffset())))
			del symbols_arm9[mangled_name]
			_create_listing_function(fi, address)
			if fi.mangled_name == '_ZN4Heap10deallocateEPv':
				print(fi.name, fi.mangled_name, hex(int(address.getOffset())))
			found_any = True
	if not found_any and not fi.is_maybe_inline:
		print(f'function {fi.name} mangled to {fi.mangled_name} and has no link location')

def make_var(vi: VarInfo):
	if vi.is_constexpr:
		return
	
	mangled_name = vi.mangled_name
	if mangled_name in symbols_arm9:
		address = symbols_arm9[mangled_name]

		symbol = symbol_table.getPrimarySymbol(address)
		space, sname = get_namespace_for(vi.name, vi.class_member)
		if symbol:
			symbol.setNameAndNamespace(sname, space, SourceType.USER_DEFINED)
		else:
			symbol_table.createLabel(address, sname, space, SourceType.USER_DEFINED)
		dt = get_ghidra_type(vi.clang_type)
		if dt.getLength() < 0:
			print(f'skipping symbol {vi.name} because the type {vi.clang_type.spelling} is incomplete')
			return
		listing.clearCodeUnits(address, address.add(dt.getLength()), False)
		listing.createData(address, dt)
	else:
		print(f'variable {vi.name} mangled to {mangled_name} and has no link location')

def main():
	print('parsing header files...')
	parse_results = header_parser.parse_project(PROJECT_ROOT, sys.argv[1:], print)

	print('parsing symbols...')
	global symbols_arm9
	symbols_arm9 = parse_symbols_file.parse_symbols(this, f'{PROJECT_ROOT}/symbols9.x')

	print('creating Ghidra types...')
	# Built-ins and C++ types
	bdtm = BuiltInDataTypeManager.getDataTypeManager()
	cat = CategoryPath('/')
	type_manager.addDataType(bdtm.getDataType('/uchar'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/schar'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/char'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/ushort'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/short'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/uint'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/int'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/ulong'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/long'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/ulonglong'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/longlong'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/bool'), conflictHandler)
	type_manager.addDataType(bdtm.getDataType('/void'), conflictHandler)
	
	# These types from NSMB-CR are problematic for Ghidra. And really they seem totally unnecessary.
	for t in nsmb_cr_types_to_ignore:
		del parse_results.classes[t]
	
	# Step 1: Create enums and (blank) structs so that all types we'll need exist.
	for name in parse_results.enums:
		create_enum(name, parse_results.enums[name])
	for name in parse_results.classes:
		create_empty_struct(name, parse_results.classes[name].is_union)
	# including typedefs and member pointer structs
	skipped_typedefs = []
	for name in parse_results.typedefs:
		if not create_typedef(parse_results.typedefs[name]):
			skipped_typedefs.append(parse_results.typedefs[name])
	while len(skipped_typedefs) > 0:
		st = []
		for t in skipped_typedefs:
			if not create_typedef(t):
				st.append(t)
		if len(st) == len(skipped_typedefs):
			raise Exception(f'Circular typedef dependency? {[(t.new_name, t.old_name) for t in st]}')
		skipped_typedefs = st
	for name in parse_results.function_member_pointers:
		create_function_type(name, parse_results.function_member_pointers[name])

	# Step 2: Populate the structs
	skipped_structs = []
	for name in parse_results.classes:
		if not populate_struct(parse_results.classes[name]):
			skipped_structs.append(parse_results.classes[name])
	while len(skipped_structs) > 0:
		ss = []
		for s in skipped_structs:
			if not populate_struct(s):
				ss.append(s)
		if len(ss) == len(skipped_structs):
			raise Exception(f'Circular struct dependency? {[s.name for s in ss]}')
		skipped_structs = ss
	
	# Step 3: Create all the functions and vtables
	for name in parse_results.classes:
		for method in parse_results.classes[name].methods:
			create_listing_function(method)
	# Validate struct sizes. Is after step 3 so that I can inspect vtables.
	for name in parse_results.classes:
		ct = parse_results.classes[name].clang_type
		gt = get_ghidra_type(ct)
		clang_size = ct.get_size()
		if clang_size >= 0:
			ghidra_size = gt.getLength()
			assert ghidra_size == clang_size, f'Incorrect size for {name}. Expected {hex(clang_size)}, got {hex(ghidra_size)}'
		else:
			gt.setDescription('Incomplete data type; full definition was not found in header files. There should not be any non-pointer references to this type.')
	# static functions
	for name in parse_results.function_defs:
		create_listing_function(parse_results.function_defs[name])
		
	# Step 4: Static variables
	for name in parse_results.static_vars:
		make_var(parse_results.static_vars[name])

	if len(symbols_arm9) != 0:
		print('Unused symbols for arm9:')
		print([s for s in symbols_arm9])

if __name__ == "__main__":
	tid = currentProgram.startTransaction('', None)
	finished = False
	try:
		main()
		finished = True
	finally:
		currentProgram.endTransaction(tid, True)
