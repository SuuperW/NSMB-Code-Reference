# Imports types, methods, and globals from header files using libclang.

#@category NDS-SRE
#@runtime PyGhidra

from importlib import reload
import os
from pathlib import Path
import sys

import parse_symbols_file
from header_parser import (
	ClassInfo,
	FunctionInfo,
	ParseResults,
	TypedefInfo,
	VarInfo,
	
	pointer_types,
	get_base_type,
	get_friendly_name)
import header_parser

# curse the ELABORATED!!
def unelaborate(t):
	while t.kind == TypeKind.ELABORATED:
		t = t.get_named_type()
	return t

from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.script import GhidraScript
from ghidra.app.services import DataTypeManagerService
from ghidra.program.flatapi import FlatProgramAPI
from ghidra.program.model.address import Address, AddressSet, AddressSpace
from ghidra.program.model.data import (
	ArrayDataType,
	BuiltInDataType,
	BuiltInDataTypeManager,
	CategoryPath,
	DataType,
	DataTypeConflictHandler,
	DataTypeManager,
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
from ghidra.program.model.listing import Function, FunctionManager, Listing, ParameterImpl, Program, VariableStorage
from ghidra.program.model.mem import Memory
from ghidra.program.model.symbol import Namespace, SourceType, SymbolTable

from clang.cindex import Cursor, CursorKind, Type, TypeKind

conflict_handler = DataTypeConflictHandler.REPLACE_HANDLER
	
class UnknownGhidraTypeException(Exception):
	pass

# Ghidra makes it difficult to manager types, by:
# 1) making it impossible to share types between multiple programs. Each program must copy a data type from a project archive, and the copies in programs will not automatically update if the project's type changes
# 2) directly referencing a type in a project archive from a program (e.g. a type in a program archive, in a program's function, or a symbol's data type) will make a copy and add it to the program EVEN IF a copy already exists. If a copy already exists, then there will now be two and the seocnd will have .conflict appended to its name
# 3) if a type that isn't in the program is implicitly referenced by marking a function as thiscall, Ghidra will create a "PlaceHolder" type but will not replace it with the real one when said data type is added to the program

class TypeGenerator:
	script: GhidraScript
	type_manager: DataTypeManager
	types_to_ignore: list[str]
	done_typedefs: set[str]
	done_structs = set[str]
	
	def __init__(self, script: GhidraScript, type_manager: DataTypeManager):
		self.script = script
		self.type_manager = type_manager
	
	def generate(self, parse_results: ParseResults, ignore: list[str]):
		self.types_to_ignore = ignore
		
		self.add_builtin_types()
			
		for t in self.types_to_ignore:
			del parse_results.classes[t]
		
		# Step 1: Create enums and (blank) structs so that all types we'll need exist.
		for name in parse_results.enums:
			self.create_enum(name, parse_results.enums[name])
		for name in parse_results.classes:
			self.create_empty_struct(name, parse_results.classes[name].is_union)
		# including typedefs and member pointer structs
		self.done_typedefs = set()
		skipped_typedefs = []
		for name in parse_results.typedefs:
			if not self.create_typedef(parse_results.typedefs[name]):
				skipped_typedefs.append(parse_results.typedefs[name])
		while len(skipped_typedefs) > 0:
			st = []
			for t in skipped_typedefs:
				if not self.create_typedef(t):
					st.append(t)
			if len(st) == len(skipped_typedefs):
				raise Exception(f'Circular typedef dependency? {[(t.new_name, t.old_name) for t in st]}')
			skipped_typedefs = st
		for name in parse_results.function_member_pointers:
			self.create_function_member_pointer(name, parse_results.function_member_pointers[name])

		# Step 2: Populate the structs and make vtables
		self.done_structs = set()
		skipped_structs = []
		for name in parse_results.classes:
			if not self.populate_struct(parse_results.classes[name]):
				skipped_structs.append(parse_results.classes[name])
		while len(skipped_structs) > 0:
			ss = []
			for s in skipped_structs:
				if not self.populate_struct(s):
					ss.append(s)
			if len(ss) == len(skipped_structs):
				raise Exception(f'Circular struct dependency? {[s.name for s in ss]}')
			skipped_structs = ss
		# Validate struct sizes.
		for name in parse_results.classes:
			ct = parse_results.classes[name].clang_type
			gt = self.get_ghidra_type(ct)
			clang_size = ct.get_size()
			if clang_size >= 0:
				ghidra_size = gt.getLength()
				assert ghidra_size == clang_size, f'Incorrect size for {name}. Expected {hex(clang_size)}, got {hex(ghidra_size)}'
			else:
				gt.setDescription('Incomplete data type; full definition was not found in header files. There should not be any non-pointer references to this type.')
	
	def add_builtin_types(self):
		bdtm = BuiltInDataTypeManager.getDataTypeManager()
		cat = CategoryPath('/')
		self.type_manager.addDataType(bdtm.getDataType('/uchar'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/schar'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/char'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/ushort'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/short'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/uint'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/int'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/ulong'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/long'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/ulonglong'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/longlong'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/bool'), conflict_handler)
		self.type_manager.addDataType(bdtm.getDataType('/void'), conflict_handler)
		
		# doy
		global clib_tm
		dtm_service = self.script.state.getTool().getService(DataTypeManagerService)
		clib_tm = None
		for dtm in dtm_service.getDataTypeManagers():
			if dtm.getName() == 'generic_clib':
				clib_tm = dtm
				break
		assert(clib_tm is not None)
		self.type_manager.addDataType(clib_tm.getDataType('/stddef.h/ptrdiff_t'), conflict_handler)
	
	def create_enum(self, name: str, clang_node: Type):
		assert(clang_node.kind == TypeKind.ENUM)
		assert(clang_node.get_size() > 0)
		
		space_names = name.split('::')
		cat = CategoryPath('/' + str.join('/', space_names[:-1]))
		name = space_names[-1]

		enum = EnumDataType(cat, name, clang_node.get_size())
		for child in clang_node.get_declaration().get_children():
			if child.kind == CursorKind.ENUM_CONSTANT_DECL:
				enum.add(child.spelling, child.enum_value)
		
		self.type_manager.addDataType(enum, conflict_handler)
	
	def create_empty_struct(self, name: str, union: bool = False):
		space_names = name.split('::')
		cat = CategoryPath('/' + str.join('/', space_names[:-1]))
		name = space_names[-1]
		
		struct: DataType
		if union:
			struct = UnionDataType(cat, name)
		else:
			struct = StructureDataType(cat, name, 0)
		struct.setExplicitPackingValue(4)

		return self.type_manager.addDataType(struct, conflict_handler)
	
	def create_typedef(self, tdef_info: TypedefInfo) -> bool:
		name = tdef_info.new_name
		if name in self.done_typedefs:
			raise Exception("TODO")
			return True
		
		_func = None
		if tdef_info.old_name == 'code*':
			try:
				_func = self.create_function_type(name + '_func', get_base_type(tdef_info.renamed_type))
				_func = self.type_manager.getPointer(_func)
			except UnknownGhidraTypeException as e:
				return False
		
		space_names = name.split('::')
		cat = CategoryPath('/' + str.join('/', space_names[:-1]))
		name = space_names[-1]
		
		dataType = _func or self.get_ghidra_type(tdef_info.renamed_type, True)
		if dataType is None:
			if tdef_info.renamed_type.kind == TypeKind.TYPEDEF and tdef_info.old_name not in self.done_typedefs:
				return False
			else:
				raise Exception(f'Could not get Ghidra type {tdef_info.old_name} for typedef {name}')
		self.done_typedefs.add(name)
			
		typedef = TypedefDataType(cat, name, dataType)
		self.type_manager.addDataType(typedef, conflict_handler)
		return True
	
	def create_function_type(self, name: str, clang_func_type: Type, param_names = None):
		"""
		Makes a Function data type, for the type manager.
		"""
		assert clang_func_type.kind == TypeKind.FUNCTIONPROTO
		
		space_names = name.split('::')
		cat = CategoryPath('/' + str.join('/', space_names[:-1]))
		name = space_names[-1]
		
		fp_args = []
		i = 0
		for arg in clang_func_type.argument_types():
			fp_args.append(ParameterDefinitionImpl(
				param_names[i] if param_names else None,
				self.get_ghidra_type(arg),
				None # comment
			))
			i += 1
		
		func_type = FunctionDefinitionDataType(cat, name)
		func_type.setArguments(*fp_args)
		func_type.setReturnType(self.get_ghidra_type(clang_func_type.get_result()))
		func_type.setCallingConvention(CompilerSpec.CALLING_CONVENTION_default)
		
		return self.type_manager.addDataType(func_type, conflict_handler)
	
	def get_ghidra_type(self, clang_or_str: Type | str, allow_none: bool = False) -> DataType | None:
		if isinstance(clang_or_str, str):
			name = clang_or_str
			ghidra_type = self.type_manager.getDataType(name)
			if not allow_none and ghidra_type is None:
				raise UnknownGhidraTypeException(f'Cannot get ghidra type {name}')
			return ghidra_type
		
		assert isinstance(clang_or_str, Type)
		clang_node = unelaborate(clang_or_str)
		
		type_name = '/' + get_friendly_name(clang_node).replace('::', '/')
		ghidra_type = self.get_ghidra_type(type_name, True)
		if ghidra_type is None:
			if clang_node.kind in pointer_types:
				ptee = clang_node.get_pointee()
				gpt = self.get_ghidra_type(ptee, allow_none)
				if gpt is not None:
					ghidra_type = self.type_manager.getPointer(gpt)
				elif allow_none:
					return None
			elif clang_node.kind in (TypeKind.CONSTANTARRAY, TypeKind.INCOMPLETEARRAY):
				atype = clang_node.get_array_element_type()
				# Incomplete arrays report size of -1. Ghidra ... we use a length of 0?
				asize = clang_node.get_array_size() if clang_node.kind == TypeKind.CONSTANTARRAY else 0
				gat = self.get_ghidra_type(atype, allow_none)
				if gat is not None:
					ghidra_type = ArrayDataType(gat, asize)
				elif allow_none:
					return None
			if ghidra_type is not None:
				ghidra_type = self.type_manager.addDataType(ghidra_type, conflict_handler)
		if ghidra_type is None and not allow_none:
			raise UnknownGhidraTypeException(f'Cannot get ghidra type {type_name} of kind {clang_node.kind} {clang_node.spelling}')
		return ghidra_type
	
	def create_function_member_pointer(self, name: str, clang_func_type: Type):
		assert clang_func_type.kind == TypeKind.MEMBERPOINTER
		class_name = get_friendly_name(clang_func_type.get_class_type())
		clang_func_type = clang_func_type.get_pointee()
		
		func_type = self.create_function_type(f'{class_name}::{name}_func', clang_func_type)
		func_type.setCallingConvention(CompilerSpec.CALLING_CONVENTION_thiscall)
		
		# Struct for the member pointer
		struct = self.create_empty_struct(name)
		func_ptr = self.type_manager.getPointer(func_type)
		struct.add(func_ptr, 0, 'func', None)
		struct.add(self.get_ghidra_type('/stddef.h/ptrdiff_t'), 0, 'offset', None)
	
	def populate_struct(self, class_info: ClassInfo):
		clang_type = class_info.clang_type
		assert header_parser.is_class_type(clang_type), clang_type.kind
		
		ghidra_type = self.get_ghidra_type('/' + class_info.name.replace('::', '/'))
		assert isinstance(ghidra_type, Structure) or isinstance(ghidra_type, Union)
		
		# Validate that subclasses have been populated first
		for subclass in class_info.subclasses:
			if subclass.name in self.types_to_ignore:
				continue
			if subclass.name not in self.done_structs:
				return False
		
		sub_vtable_type = None
		sub_vtable_index = 0
		for subclass in class_info.subclasses:
			if subclass.name in self.types_to_ignore:
				continue
			for sub_field in self.get_ghidra_type(subclass.clang_type).getComponents():
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
			vtable_type = self.create_empty_struct(f'{class_info.name}::vtable')
			vtable_ptr_type = self.type_manager.getPointer(vtable_type)
			if sub_vtable_type is not None:
				# Should it stay where it is, or move to index 0? I don't know of a type in NSMB I can check.
				if sub_vtable_index != 0:
					print(f'Type {class_info.name} has a vtable not at index 0. Check me.')
				vtable_type.replaceWith(sub_vtable_type)
				ghidra_type.replace(sub_vtable_index, vtable_ptr_type, 0, 'vtable', None)
			else:
				ghidra_type.insert(0, vtable_ptr_type, 0, 'vtable', None)
			for method in vtable_methods:
				func_type = self.get_ghidra_type('/' + method.name.replace('::', '/'), True)
				if func_type is None:
					func_type = self.create_function_type(method.name, method.clang_type, method.param_names)
				func_ptr_type = self.type_manager.getPointer(func_type)
				if '::~' in method.name:
					# vtables contain destructors D1 then D0
					vtable_type.add(func_ptr_type, 0, '~D1', None)
					vtable_type.add(func_ptr_type, 0, '~D0', None)
				else:
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
					ghidra_type.add(self.get_ghidra_type('/u8'), 0, f'padding_{padding_count}', None)
					padding_count += 1
			if 'anonymous ' in field_name:
				field_name = f'anon_{anon_field_count}'
				anon_field_count += 1
			if ftype.kind == TypeKind.POINTER and unelaborate(ftype.get_pointee()).kind == TypeKind.FUNCTIONPROTO:
				tname = f'/{class_info.name.replace('::', '/')}/{field_name}_func'
				field_ghidra_type = self.get_ghidra_type(tname)
				assert field_ghidra_type is not None, tname
				field_ghidra_type = self.type_manager.getPointer(field_ghidra_type)
			else:
				field_ghidra_type = self.get_ghidra_type(ftype)
			
			bits = field.get_bitfield_width()
			if bits == -1:
				ghidra_type.add(field_ghidra_type, 0, field_name, None)
			else:
				ghidra_type.addBitField(field_ghidra_type, bits, field_name, None)
		
		self.done_structs.add(class_info.name)
		return True

ctor_variants = ['C1', 'C2', 'C3', 'CI1', 'CI2']
dtor_variants = ['D1', 'D0', 'D2']

class SymbolGenerator:
	program: Program
	function_manager: FunctionManager
	listing: Listing
	flat_api: FlatProgramAPI
	symbol_table: SymbolTable
	var_storage: dict[int, VariableStorage]
	mem: Memory
	
	type_manager: DataTypeManager
	tpye_source: DataTypeManager
	
	report_symbols: bool
	symbols_arm9: dict[str, (int, str)]
	overlay_spaces: dict[int, AddressSpace]
	ghidra_namespaces: dict[str, Namespace]

	def __init__(self, program: Program, type_source: DataTypeManager):
		self.program = program
		self.function_manager = self.program.getFunctionManager()
		self.listing = self.program.getListing()
		self.flat_api = FlatProgramAPI(self.program)
		self.symbol_table = self.program.getSymbolTable()
		self.mem = self.program.getMemory()
		
		self.type_manager = self.program.getDataTypeManager()
		self.type_source = type_source
		
		self.ghidra_namespaces = {}
		
		# Ghidra will want to put parameters larger than 4 bytes on the stack, even if r0-r3 haven't been used yet.
		# So we gotta fix that.
		r0 = self.program.getRegister('r0')
		r1 = self.program.getRegister('r1')
		r2 = self.program.getRegister('r2')
		r3 = self.program.getRegister('r3')
		param_registers = [r0, r1, r2, r3]
		self.var_storage = {}
		for i in range(4):
			# Ghidra won't allow partial register storage, so some of these will be invalid and we won't use them.
			self.var_storage[i << 8 | 1] = VariableStorage(self.program, param_registers[i])
			self.var_storage[i << 8 | 2] = VariableStorage(self.program, *param_registers[i:i+2])
			self.var_storage[i << 8 | 3] = VariableStorage(self.program, *param_registers[i:i+3])
			self.var_storage[i << 8 | 4] = VariableStorage(self.program, *param_registers[i:i+4])
	
	def generate(self,
	  parse_results: ParseResults,
	  symbols: dict[str, (int, str)],
	  overlay_spaces: dict[int, AddressSpace],
	  report_symbols: bool):
		self.report_symbols = report_symbols
		self.symbols_arm9 = dict(symbols)
		self.overlay_spaces = overlay_spaces
			
		# Step 3: Create all the functions
		for name in parse_results.classes:
			for method in parse_results.classes[name].methods:
				self.create_listing_function(method)
		
		# static functions
		for name in parse_results.function_defs:
			self.create_listing_function(parse_results.function_defs[name])
			
		# Step 4: Static variables, must happen after all functions because we use clearCodeUnits(0x4000) at each function.
		for name in parse_results.static_vars:
			self.make_var_vi(parse_results.static_vars[name])
		# vtables
		for name in parse_results.classes:
			self.make_vtable_symbol(parse_results.classes[name])
			
		# ensure we haven't allowed Ghidra to create "PlaceHolder" or conflict types
		for dt in self.type_manager.getAllDataTypes():
			if dt.getDescription().startswith('PlaceHolder') or dt.getName().endswith('.conflict'):
				raise Exception(dt.getPathName())
		
		if self.report_symbols and len(self.symbols_arm9) != 0:
			print('Unused symbols for arm9 (limit 1000):')
			print([s for s in self.symbols_arm9][:1000])
	
	def _create_listing_function(self, fi: FunctionInfo, address: Address) -> Function:
		parent_namespace, fname = self.get_namespace_for(fi.name, fi.class_member)
		
		# Make or get function
		func = self.function_manager.getFunctionAt(address)
		if func is not None:
			if func.getName(True) == fi.name:
				if fi.is_ctor or fi.is_dtor:
					return func # expected
				else:
					raise Exception(f'??? {fname} {hex(address.getOffset())}')
			func.setName(fname, SourceType.USER_DEFINED)
		else:
			# Ghidra may have auto-generated a symbol that we need to delete
			clear_data = self.listing.getDataAt(address) is not None
			if clear_data:
				# We don't know how big the function will be! Guess a large value.
				self.listing.clearCodeUnits(address, address.add(0x4000), False)
			func = self.flat_api.createFunction(address, fname)
			if func is None:
				raise Exception(f'Could not create function {fname} at {address}')
			# This turns out to be rather complicated. Instead we'll let auto-analyze run after this script.
			#if clear_data:
			#	dc = DisassembleCommand(address, AddressSet(address, address.add(0x4000)), False)
			#	dc.applyTo(currentProgram)
		
		# Set function properties
		if fi.is_thiscall:
			# Ghidra requires this type exist first, or it will mess up the type now and then AGAIN when parameters are set.
			self.get_ghidra_type('/' + parent_namespace.getName(True).replace('::', '/'))
			func.setCallingConvention(CompilerSpec.CALLING_CONVENTION_thiscall)
		else:
			func.setCallingConvention(CompilerSpec.CALLING_CONVENTION_default)
		func.setParentNamespace(parent_namespace)
		func.setReturnType(self.get_ghidra_type(fi.clang_type.get_result()), SourceType.USER_DEFINED)
		
		# Function parameters are hard. Because Ghidra thinks registers should not be used for >4 byte params.
		# And when any params have custom storage, all of them have to.
		func_params = []
		i = 0
		reg_num = 0
		def basic_add_param(pname: str, dt: DataType):
			rcount = ((dt.getLength() + 3) >> 2)
			if reg_num < 4:
				storage = self.var_storage[reg_num << 8 | rcount]
			else:
				storage = VariableStorage(self.program, (reg_num - 4) * 4, dt.getLength())
			func_params.append(ParameterImpl(pname, dt, storage, self.program))
			return rcount
		# With custom storage params, we need to expicitly include the this param!
		if fi.is_thiscall:
			owning_type_name = str.join('/', fi.name.split('::')[:-1])
			owning_type = self.get_ghidra_type('/' + owning_type_name)
			reg_num += basic_add_param('this', self.type_manager.getPointer(owning_type))
		for param in fi.clang_type.argument_types():
			param_type = self.get_ghidra_type(param)
			registers_used = (param_type.getLength() + 3) >> 2
			if reg_num < 4 and registers_used + reg_num > 4:
				# Further, Ghidra won't allow partial register storage. SO WE GOTTA SPLIT IT UP.
				vars_made = 0
				while vars_made < registers_used:
					reg_num += basic_add_param(f'{fi.param_names[i]}_{vars_made}', self.get_ghidra_type('/u32'))
					vars_made += 1
			else:
				reg_num += basic_add_param(fi.param_names[i], param_type)
			i += 1
		func.replaceParameters(
			Function.FunctionUpdateType.CUSTOM_STORAGE, # CUSTOM_STORAGE, DYNAMIC_STORAGE_ALL_PARAMS
			True,
			SourceType.USER_DEFINED,
			*func_params)
		return func
	
	def create_listing_function(self, fi: FunctionInfo):
		variants = [None]
		if fi.is_ctor:
			variants = ctor_variants
		elif fi.is_dtor:
			variants = dtor_variants
		found_any = False
		for variant in variants:
			mangled_name = fi.mangled_name
			if variant is not None:
				# We're just going to assume the mangled name doesn't contain extra C1E etc substrings
				mangled_name = mangled_name.replace(f'{variant[:-1]}1E', f'{variant}E')
			if mangled_name in self.symbols_arm9:
				tup = self.symbols_arm9[mangled_name]
				address = self.resolve_address(tup[0], tup[1])
				if address is None:
					return
				del self.symbols_arm9[mangled_name]
				tor = self._create_listing_function(fi, address)
				found_any = True
				if variant is not None:
					comment = tor.getRepeatableComment()
					if comment is None:
						comment = variant
					else:
						comment = f'{comment}, {variant}'
					tor.setRepeatableComment(comment)
		if self.report_symbols and not found_any and not fi.is_maybe_inline:
			print(f'function {fi.name} mangled to {fi.mangled_name} and has no link location')
	
	def get_namespace_for(self, name: str, is_class: bool) -> (Namespace, str):
		if '::' not in name:
			return (self.program.getGlobalNamespace(), name)
		index = name.rindex('::')
		namespace_full = name[:index]
		label_name = name[index+2:]
		if namespace_full in self.ghidra_namespaces:
			return (self.ghidra_namespaces[namespace_full], label_name)
		
		namespace_parent, namespace_last = self.get_namespace_for(namespace_full, is_class)
		namespace = self.symbol_table.getNamespace(namespace_last, namespace_parent)
		if namespace is None:
			if is_class:
				namespace = self.symbol_table.createClass(
					namespace_parent,
					namespace_last,
					SourceType.USER_DEFINED)
			else:
				namespace = self.symbol_table.createNameSpace(
					namespace_parent,
					namespace_last,
					SourceType.USER_DEFINED)
		
		self.ghidra_namespaces[namespace_full] = namespace
		return (namespace, label_name)
	
	def get_ghidra_type(self, clang_or_str: Type | str, allow_none: bool = False) -> DataType | None:
		if isinstance(clang_or_str, str):
			name = clang_or_str
			ghidra_type = self.type_manager.getDataType(name)
			if ghidra_type is None:
				ghidra_type = self.type_source.getDataType(name)
				if ghidra_type is None:
					if not allow_none:
						raise UnknownGhidraTypeException(f'Cannot get ghidra type {name}')
					return None
				ghidra_type = self.type_manager.addDataType(ghidra_type, conflict_handler)
			return ghidra_type
		
		assert isinstance(clang_or_str, Type)
		clang_node = unelaborate(clang_or_str)
		
		type_name = '/' + get_friendly_name(clang_node).replace('::', '/')
		ghidra_type = self.get_ghidra_type(type_name, True)
		if ghidra_type is None:
			if clang_node.kind in pointer_types:
				ptee = clang_node.get_pointee()
				gpt = self.get_ghidra_type(ptee, allow_none)
				if gpt is not None:
					ghidra_type = self.type_manager.getPointer(gpt)
				elif allow_none:
					return None
			elif clang_node.kind in (TypeKind.CONSTANTARRAY, TypeKind.INCOMPLETEARRAY):
				atype = clang_node.get_array_element_type()
				# Incomplete arrays report size of -1. Ghidra ... we use a length of 0?
				asize = clang_node.get_array_size() if clang_node.kind == TypeKind.CONSTANTARRAY else 0
				gat = self.get_ghidra_type(atype, allow_none)
				if gat is not None:
					ghidra_type = ArrayDataType(gat, asize)
				elif allow_none:
					return None
			if ghidra_type is not None:
				ghidra_type = self.type_manager.addDataType(ghidra_type, conflict_handler)
		if ghidra_type is None and not allow_none:
			raise UnknownGhidraTypeException(f'Cannot get ghidra type {type_name} of kind {clang_node.kind} {clang_node.spelling}')
		return ghidra_type
	
	def resolve_address(self, overlay_id: int, addr_str: str) -> Address:
		space = self.overlay_spaces.get(overlay_id)
		if space is None:
			if self.report_symbols:
				raise Exception(f'No such space {overlay_id}.')
			return None
		addr = space.getAddress(addr_str)
		if self.mem.getBlock(addr) is None:
			if self.report_symbols:
				raise Exception(f'Failed to resolve address {space.getName()}:{addr_str} for overlay {overlay_id}.')
			return None
		return addr
	
	def make_var(self, mangled_name: str, plain_name: str, is_class_member: bool, ghidra_type: Structure):
		assert ghidra_type is not None
		if mangled_name in self.symbols_arm9:
			if ghidra_type.getLength() < 0 and self.report_symbols:
				print(f'skipping symbol {plain_name} because the type {ghidra_type.getName()} is incomplete')
				return
			tup = self.symbols_arm9[mangled_name]
			address = self.resolve_address(tup[0], tup[1])
			if address is None:
				return
			if mangled_name.startswith('_ZTV'):
				# Virtual tables: The symbol points to the start of the vtable object.
				# But pointers in memory to the vtable point to its address point.
				# The vtable data structures we've made for Ghidra also begin at the address point.
				# So, we will move the address here to the vtable's address point.
				# And we assume that the difference is 8 bytes.
				address = address.add(8)
			
			space, sname = self.get_namespace_for(plain_name, is_class_member)
			symbols = self.symbol_table.getSymbols(address)
			# If there are other symbols that we made, that's OK as long as the data types match.
			existing_data_type: DataType | None = None
			for s in symbols:
				if s.getName(True) == plain_name:
					return
				if s.getSource() == SourceType.USER_DEFINED:
					if existing_data_type is None:
						existing_data_type = self.listing.getDataAt(address).getDataType()
					# Instances may be different even when the types are the same.
					if existing_data_type.getPathName() != ghidra_type.getPathName():
						raise Exception(f'Cannot have two different data types at the same address. {s.getName(True)} exists with {existing_data_type.getPathName()} at {address} and we tried to make {plain_name} with {ghidra_type.getPathName()}.')
			# If the only symbol is a default symbol, it will be overwritten.
			self.symbol_table.createLabel(address, sname, space, SourceType.USER_DEFINED)
			if existing_data_type is None:
				self.listing.clearCodeUnits(address, address.add(ghidra_type.getLength() - 1), False)
				self.listing.createData(address, ghidra_type)
		elif self.report_symbols:
			print(f'variable {plain_name} mangled to {mangled_name} and has no link location')
	
	def make_var_vi(self, vi: VarInfo):
		if vi.is_constexpr:
			return
		self.make_var(vi.mangled_name, vi.name, vi.class_member, self.get_ghidra_type(vi.clang_type))
	
	def make_vtable_symbol(self, ci: ClassInfo):
		owner_name = ci.get_vtable_owner_name()
		if owner_name is None:
			return
		vtable_mangled_name: str
		if '::' in ci.name:
			parts = ci.name.split('::')
			parts = [f'{len(p)}{p}' for p in parts]
			vtable_mangled_name = f'_ZTVN{str.join('', parts)}E'
		else:
			vtable_mangled_name = f'_ZTV{len(ci.name)}{ci.name}'
		plain_name = f'{ci.name}::vtable'
		owner_name = owner_name.replace('::', '/')
		ghidra_vtable = self.get_ghidra_type(f'/{owner_name}/vtable')
		self.make_var(vtable_mangled_name, plain_name, True, ghidra_vtable)
# end
