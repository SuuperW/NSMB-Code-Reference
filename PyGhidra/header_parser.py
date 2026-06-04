from __future__ import annotations
from collections.abc import Container
import os
from pathlib import Path
import subprocess
from typing import Callable

from clang.cindex import (
	Config,
	Cursor,
	CursorKind,
	Index,
	SourceLocation,
	SourceRange,
	TranslationUnit,
	Type,
	TypeKind,
)

LLVM_LIB = os.environ.get('LIBCLANG_PATH')
if LLVM_LIB is not None:
	assert Path(LLVM_LIB).exists(), f'could not find LLVM at {LLVM_LIB}'
if LLVM_LIB is not None:
	Config.set_library_file(LLVM_LIB)

class TypedefInfo:
	new_name: str
	old_name: str

	def __init__(self, new_name, old_name):
		self.new_name = new_name
		self.old_name = old_name

class FunctionTypedefInfo(TypedefInfo):
	param_names: list[str] | None
	param_types: list[str]
	return_type: str
	
	def __init__(self, new_name, param_names, param_types, return_type):
		self.new_name = new_name
		self.old_name = 'code*'
		self.param_names = param_names
		self.param_types = param_types
		self.return_type = return_type

# This class should eventually go away, in favor of a ClassInfo + FunctionTypedefInfo
class MemberPointerTypedefInfo(TypedefInfo):
	clang_type: Type
	
	def __init__(self, new_name, old_name, clang_type):
		self.new_name = new_name
		self.old_name = old_name
		self.clang_type = clang_type

class FunctionInfo:
	name: str
	mangled_name: str
	
	is_thiscall: bool
	is_static: bool
	is_virtual: bool
	is_pure_virtual: bool
	is_ctor: bool
	is_dtor: bool
	is_maybe_inline: bool
	is_consteval: bool
	
	class_member: bool
	
	typedef: FunctionTypedefInfo
	
	def __init__(self, class_name: str | None, node: Cursor, fti: FunctionTypedefInfo):
		assert node.kind in (CursorKind.CXX_METHOD, CursorKind.CONSTRUCTOR, CursorKind.DESTRUCTOR, CursorKind.FUNCTION_DECL, CursorKind.CONVERSION_FUNCTION), node.kind
		
		if class_name is None:
			self.name = node.spelling
			self.class_member = False
		else:
			self.name = f'{class_name}::{node.spelling}'
			self.class_member = True
		self.name = self.name.replace(' ', '_') # operators
		self.mangled_name = node.mangled_name
		
		self.is_static = node.is_static_method() or not self.class_member
		self.is_thiscall = not self.is_static
		# Note: libclang will report non-virtual if the virtual specifier is not present.
		# This is not a problem for us, since the subclass's method will be found when listing virtual methods.
		self.is_virtual = node.is_virtual_method()
		self.is_pure_virtual = node.is_pure_virtual_method()
		self.is_ctor = node.kind == CursorKind.CONSTRUCTOR
		self.is_dtor = node.kind == CursorKind.DESTRUCTOR
		
		# Methods can be inlined with the inline specifier, attributes, constexpr, or consteval.
		# Libclang does not expose any of those things (except attributes, partially).
		# So, tokens. And it's weird because of ??? sometimes the default extent is invalid???
		self.is_maybe_inline = False
		self.is_consteval = False
		start = node.extent.start
		start = SourceLocation.from_position(node.translation_unit, start.file, start.line, start.column)
		end = node.extent.end
		end = SourceLocation.from_position(node.translation_unit, end.file, end.line, end.column)
		for t in node.translation_unit.get_tokens(extent=SourceRange.from_locations(start, end)):
			if t.spelling in ('inline', 'constexpr'):
				self.is_maybe_inline = True
			elif t.spelling == 'consteval':
				self.is_consteval = True
			elif t.spelling in ('NTR_CREATE_BITMASK_ENUM', 'NTR_INLINE'): # NSMB-CR macros
				self.is_maybe_inline = True
			elif t.spelling == '{':
				break

		self.typedef = fti

	def get_signature_with_name(self):
		"""Replaces destructor name with just a ~, so that signature can be compared with base class"""
		name = self.name
		if '~' in self.name:
			name = '~'
		else:
			name = name.split('::')[-1]
		params_sig = str.join(', ', self.typedef.param_types)
		return f'{self.typedef.return_type} {name}({params_sig})'

class ClassInfo:
	clang_type: Type
	name: str
	subclasses: list[ClassInfo]
	methods: list[FunctionInfo]
	aligned_fields: list[str]
	
	is_union: bool
	
	_vtable_methods: list[FunctionInfo]
	
	def __init__(self, clang_type: Type):
		self.clang_type = clang_type
		self.name = get_friendly_name(clang_type)
		self.subclasses = []
		self.methods = []
		self.aligned_fields = []
		
		self.is_union = clang_type.get_declaration().kind == CursorKind.UNION_DECL
		
		self._vtable_methods = None
	
	def add_subclass(self, subclass: ClassInfo):
		self.subclasses.append(subclass)
	def add_method(self, method: FunctionInfo):
		self.methods.append(method)
		
	def _get_virtuals(self) -> list[str]:
		virtual_methods = [m for m in self.methods if m.is_virtual]
		virtual_methods = [m.get_signature_with_name() for m in virtual_methods]
		
		for subclass in self.subclasses:
			svm = subclass._get_virtuals()
			for m in svm:
				if m not in virtual_methods:
					virtual_methods.append(m)
		
		return virtual_methods
		
	def vtable_methods(self) -> list[FunctionInfo]:
		if self._vtable_methods:
			return self._vtable_methods
		
		virtual_methods = [m for m in self.methods if m.is_virtual]
		vm_strs = [m.get_signature_with_name() for m in virtual_methods]
		
		for subclass in self.subclasses:
			svm = subclass._get_virtuals()
			for m in svm:
				if m in vm_strs:
					index = vm_strs.index(m)
					del virtual_methods[index]
					del vm_strs[index]
		
		self._vtable_methods = virtual_methods
		return virtual_methods
	
	def get_vtable_owner_name(self) -> str | None:
		if len(self.vtable_methods()) != 0:
			return self.name
		for sub in self.subclasses:
			so = sub.get_vtable_owner_name()
			if so is not None:
				return so
		return None

class VarInfo:
	name: str
	mangled_name: str
	clang_type: Type
	class_member: bool
	is_constexpr: bool
	
	def __init__(self, name, cursor, class_member):
		self.name = name
		self.mangled_name = cursor.mangled_name
		self.clang_type = cursor.type
		self.class_member = class_member
		
		self.is_constexpr = False
		for t in cursor.get_tokens():
			if t.spelling == 'constexpr':
				self.is_constexpr = True


# --- Project path stuff
project_include_path = ''
def is_in_project_file(cursor: Cursor) -> bool:
	loc = cursor.location
	if bool(loc.file):
		# libclang is not consistent with paths being relative/absolute nor with which slash is used
		fname = get_full_path(str(loc.file)).replace('\\', '/')
		return fname.startswith(project_include_path)
	return False

path_map = {}
def get_full_path(path: str):
	# Using pathlib to more properly check paths is very slow (since we'll be doing this many thousands of times)
	# This works.
	mapped = path_map.get(path)
	if mapped is None:
		mapped = str(Path(path).resolve()) # stats file; slow
		path_map[path] = mapped
	return mapped

# --- Clang type + name helpers
pointer_types = (TypeKind.POINTER, TypeKind.LVALUEREFERENCE, TypeKind.RVALUEREFERENCE)
def unelaborate(t: Type):
	while t.kind == TypeKind.ELABORATED:
		t = t.get_named_type()
	return t

def get_base_type(t: Type):
	"""If t is a pointer or array, returns the type it points to. (if that is a pointer/array, then its base type)"""
	b = None
	t = unelaborate(t)
	if t.kind in pointer_types:
		b = t.get_pointee()
	elif t.kind == TypeKind.CONSTANTARRAY:
		b = t.get_array_element_type()
	elif t.kind == TypeKind.INCOMPLETEARRAY:
		b = t.get_array_element_type()
	elif t.kind == TypeKind.AUTO:
		b = t.get_canonical()

	if b is None:
		return unelaborate(t)
	else:
		return get_base_type(b)

def is_class_type(t: Type):
	t = unelaborate(t)
	return t.kind == TypeKind.RECORD or (t.kind == TypeKind.UNEXPOSED and t.get_num_template_arguments() > 0)

anonymous_names: dict[str, str] = {}
def get_friendly_name(clang_type: Type, node = None) -> str:
	if node is None:
		node = clang_type.get_declaration()

	clang_type = unelaborate(clang_type)

	if clang_type.kind == TypeKind.TYPEDEF:
		return clang_type.spelling
	elif clang_type.kind in pointer_types:
		ptee = clang_type.get_pointee()
		if ptee.kind in (TypeKind.VOID, TypeKind.INVALID):
			return "void*"
		return f"{get_friendly_name(ptee, node)}*"
	elif clang_type.kind == TypeKind.CONSTANTARRAY:
		ptee = clang_type.get_array_element_type()
		return f"{get_friendly_name(ptee, node)}[{clang_type.get_array_size()}]"
	elif clang_type.kind == TypeKind.INCOMPLETEARRAY:
		ptee = clang_type.get_array_element_type()
		return f"{get_friendly_name(ptee, node)}[]"

	elif clang_type.kind in (TypeKind.FUNCTIONPROTO, TypeKind.FUNCTIONNOPROTO):
		return 'code'

	elif clang_type.kind == TypeKind.VOID:
		return 'void'

	elif clang_type.kind == TypeKind.BOOL:
		return 'bool'
		
	elif clang_type.kind == TypeKind.MEMBERPOINTER:
		return 'member pointer'
		
	elif clang_type.kind == TypeKind.LVALUEREFERENCE:
		return get_friendly_name(clang_type.get_pointee())
	
	tag = None
	if clang_type.kind == TypeKind.ENUM:
		tag = clang_type.spelling.replace('enum ', '')
	elif is_class_type(clang_type):
		tag = clang_type.spelling.replace('struct ', '').replace('union ', '')
	elif clang_type.is_pod():
		tag = clang_type.spelling
	if tag is not None:
		if 'anonymous ' in tag or 'unnamed ' in tag:
			if tag not in anonymous_names:
				namespace_prefix = ''
				if '::' in tag:
					namespace_prefix = tag[:tag.rindex('::')+2]
				anonymous_names[tag] = f'{namespace_prefix}anon_{len(anonymous_names)}'
			return anonymous_names[tag]
		tag = tag.replace('const ', '')
		# rename for Ghidra
		tag = tag.replace('unsigned ', 'u').replace('long ', 'long')
		tag = tag.replace('signed char', 'schar').replace('signed ', '')
		return tag.strip()

	raise Exception(f'unknown type in get_friendly_name {clang_type.spelling} at {node.location} and is {clang_type.kind}')

def is_function_pointer(clang_type: Type) -> bool:
	if clang_type.kind not in pointer_types:
		return False
	ptee = clang_type.get_pointee()
	return ptee.kind == TypeKind.FUNCTIONPROTO

# --- Collection
collectable_type_declarations = (
	CursorKind.TYPEDEF_DECL,
	CursorKind.ENUM_DECL,
	CursorKind.STRUCT_DECL,
	CursorKind.UNION_DECL,
	CursorKind.CLASS_DECL,
)

class ParseResults:
	classes: dict[str, ClassInfo]
	typedefs: dict[str, TypedefInfo]
	enums: dict[str, Type]
	function_member_pointers: dict[str, Type]
	function_defs: dict[str, FunctionInfo]
	static_vars: dict[str, VarInfo]
	
	_known_symbols: Container[str]
	
	# libclang does not handle class templates very well
	# The template definition does not have a valid type (ok, I guess)
	# Variables who's type is a template instance have an incomplete type
	# This incomplete type does not reference the main type, or present any way to get a completed version.
	# Non-template classes which inherit from a template instance have a subclass type for that template instance which is complete*.
	# 	*but there is no corresponding definition Cursor, which we need.
	# So we'll need to track the cursor for the template definition, plus the instantiating types. And then combine.
	# This is not implemented yet.
	_incomplete_template_instances: dict[str, Type]
	_class_template_cursors: dict[str, Cursor]
	
	_namespace: str | None # Type.spelling includes namespace automatically, but Cursor.spelling does not.
	_seen_usrs: set[str] # Unified Symbol Resolution
	_collected_type_decls: set[tuple[str, int]]
	_anonymous_function_count: int
	
	_unsupported_messages: set[str]
	
	def __init__(self, tu: TranslationUnit, known_symbols: Container[str]):
		self.classes = {}
		self.typedefs = {}
		self.enums = {}
		self.function_member_pointers = {}
		self.function_defs = {}
		self.static_vars = {}
		
		self._known_symbols = known_symbols
		self._namespace = None
		self._seen_usrs = set()
		self._collected_type_decls = set()
		self._anonymous_function_count = 0
		
		self._incomplete_template_instances = {}
		self._class_template_cursors = {}
		
		self._unsupported_messages = set()
		
		self.collect(tu.cursor)

	def append_namespace(self, symbol: str, class_namespace: str | None) -> str:
		if class_namespace is not None:
			return f'{class_namespace}::{symbol}'
		elif self._namespace is not None:
			return f'{self._namespace}::{symbol}'
		else:
			return symbol

	def collect_type_members(self, node: Type) -> ClassInfo:
		node = unelaborate(node)
		ci = ClassInfo(node)
		
		if node.kind == TypeKind.UNEXPOSED and node.get_num_template_arguments() > 0 and node.get_size() < 0:
			self._incomplete_template_instances[ci.name] = node
			return ci
		
		if ci.name in self.classes:
			raise Exception(f'Duplicate class {ci.name}')
		self.classes[ci.name] = ci
		
		for field in node.get_fields():
			self.collect_var_or_field(field, ci.name)
			for fc in field.get_children():
				if fc.kind == CursorKind.ALIGNED_ATTR:
					ci.aligned_fields.append(field.spelling) # libclang doesn't expose the number
					break
		for child in node.get_declaration().get_children():
			if child.kind == CursorKind.CXX_BASE_SPECIFIER:
				sub_name = get_friendly_name(child.type)
				if sub_name not in self.classes:
					self.collect_type(child.type)
				ci.add_subclass(self.classes[sub_name])
			elif child.kind in (CursorKind.CXX_METHOD, CursorKind.CONSTRUCTOR, CursorKind.DESTRUCTOR, CursorKind.CONVERSION_FUNCTION):
				pure_virtual = child.is_pure_virtual_method()
				if not child.is_deleted_method() and not pure_virtual:
					self.collect_function_info(child, ci)
				elif pure_virtual:
					fi = FunctionInfo(ci.name, child, self.get_typedef_info('', child))
					ci.add_method(fi)
			elif child.kind == CursorKind.VAR_DECL:
				self.collect_var_or_field(child, ci.name)
			elif child.kind in collectable_type_declarations:
				self.collect_type(child.type)
			elif child.kind == CursorKind.CLASS_TEMPLATE:
				self._class_template_cursors[child.spelling] = child
				#print(f'Templates not yet fully supported. {node.spelling}')
			elif child.kind not in (CursorKind.FIELD_DECL, CursorKind.CXX_ACCESS_SPEC_DECL, CursorKind.FUNCTION_TEMPLATE, CursorKind.TYPE_ALIAS_DECL, CursorKind.CXX_BOOL_LITERAL_EXPR, CursorKind.TYPE_REF, CursorKind.STATIC_ASSERT, CursorKind.ALIGNED_ATTR):
				# should I be ignoring TYPE_ALIAS_DECL?
				print('unknown child cursor kind', child.kind, child.spelling, node.spelling, child.location)
		return ci
	
	def collect_type_ti(self, ti: TypedefInfo):
		if isinstance(ti, MemberPointerTypedefInfo):
			assert ti.new_name not in self.function_member_pointers, f'Duplicate member pointer {ti.new_name}'
			self.function_member_pointers[ti.new_name] = ti.clang_type
			self.get_typedef_info('', ti.clang_type) # collects referenced types
		else:
			assert ti.new_name not in self.typedefs, f'Duplicate typedef {ti.new_name}'
			self.typedefs[ti.new_name] = ti
	
	def is_type_collected(self, clang_type: Type) -> bool:
		# We can mostly rely on Unified Symbol Resolution to distinguish between types.
		# But this fails with anonymous types. Multiple anonymous types within a struct have the same USR.
		# So we also use Cursor.hash.
		# Cursor.hash cannot be used alone because different template instantiations have the same declaration cursor.
		# But also we cannot include the hash for non-anonymous types because certain typedefs do get defined twice, with different cursors. (e.g. size_t in the standard library)
		
		if clang_type.kind == TypeKind.FUNCTIONPROTO:
			# We can't really track these, so each collection will be its own type.
			return False
		
		type_decl = clang_type.get_declaration()
		if clang_type.kind == TypeKind.UNEXPOSED and type_decl.kind == CursorKind.NO_DECL_FOUND:
			# https://github.com/llvm/llvm-project/issues/192268
			clang_type = clang_type.get_canonical()
			type_decl = clang_type.get_declaration()
		
		if clang_type.kind.value < TypeKind.COMPLEX.value and clang_type.kind.value >= TypeKind.VOID.value:
			return get_friendly_name(clang_type) # built-in type
		
		maybe_hash = type_decl.hash if 'anonymous ' in clang_type.spelling else 0
		usr_hash = (str(type_decl.get_usr()), maybe_hash)
		if usr_hash in self._collected_type_decls:
			return True
		
		self._collected_type_decls.add(usr_hash)
		return False
		
	def get_typedef_info(self, name: str, node: Type | Cursor) -> TypedefInfo | None:
		clang_type: Type
		cursor: Cursor | None
		if isinstance(node, Type):
			clang_type = node
			cursor = None
		else:
			clang_type = node.type
			cursor = node
		
		underlying = unelaborate(clang_type)
		underlying_name = get_friendly_name(underlying)
		
		if name != underlying_name:
			if is_function_pointer(underlying) or underlying.kind == TypeKind.FUNCTIONPROTO:
				underlying = get_base_type(underlying)
				param_names = []
				param_types = []
				if cursor is not None:
					for arg in cursor.get_arguments():
						param_names.append(arg.spelling)
						param_types.append(self.collect_type(arg.type))
				else:
					param_names = None
					for arg in underlying.argument_types():
						param_types.append(self.collect_type(arg))
				return FunctionTypedefInfo(
					new_name = name,
					param_names = param_names,
					param_types = param_types,
					return_type = self.collect_type(underlying.get_result()),
				)
			elif underlying.kind == TypeKind.MEMBERPOINTER:
				return MemberPointerTypedefInfo(name, underlying_name, clang_type)
			else:
				self.collect_type(underlying)
				return TypedefInfo(name, underlying_name)

		if underlying.kind in (TypeKind.RECORD, TypeKind.ENUM):
			# this happens for typedef struct Foo {} Foo, since we remove 'struct '
			self.collect_type(underlying)
			return None
		else:
			raise Exception(f'Unexpected same-name typedef {name} = {underlying.spelling}, {underlying.kind}')
	
	def collect_type(self, node: Type, name_for_func: str | None = None) -> str:
		"""Returns the friendly name of the given Type"""
		friendly_name = get_friendly_name(node)
		node = get_base_type(node)
		if self.is_type_collected(node):
			return friendly_name
		
		if node.kind == TypeKind.TYPEDEF:
			tdef_name = get_friendly_name(node)
			ti = self.get_typedef_info(tdef_name, node.get_declaration().underlying_typedef_type)
			if ti is not None:
				self.collect_type_ti(ti)
		# struct/union/class
		elif is_class_type(node):
			self.collect_type_members(node)
		# enum
		elif node.kind == TypeKind.ENUM:
			enum_name = get_friendly_name(node)
			assert enum_name not in self.enums, f'Duplicate enum {enum_name}'
			self.enums[enum_name] = node
		# function pointer (we will not have pointer to here, because we did get_base_type)
		elif node.kind == TypeKind.FUNCTIONPROTO:
			if name_for_func is None:
				name_for_func = f'anon_func_{self._anonymous_function_count}'
				self._anonymous_function_count += 1
			else:
				name_for_func += '_func'
			ti = self.get_typedef_info(name_for_func, node)
			self.collect_type_ti(ti)
			return ti.new_name + '*'
		elif node.kind == TypeKind.MEMBERPOINTER:
			# not implemented
			raise Exception('anonymous member pointer not supported')
		
		return friendly_name
	
	def collect_var_or_field(self, var_decl: Cursor, class_name: str | None = None):
		var_name = self.append_namespace(var_decl.spelling, class_name)
		self.collect_type(var_decl.type, var_name)
		
		if var_decl.kind == CursorKind.FIELD_DECL:
			return
		
		vi = VarInfo(var_name, var_decl, class_name is not None)
		if vi.mangled_name in self.static_vars:
			raise Exception(f'Duplicate var {vi.name} {vi.mangled_name} {var_decl.location}')
		self.static_vars[vi.mangled_name] = vi

	def collect_function_info(self, node: Cursor, ci: ClassInfo | None = None):
		class_name = None if ci is None else ci.name
		ti = self.get_typedef_info('', node)
		fi = FunctionInfo(class_name, node, ti)
		if fi.is_consteval:
			return # the function won't exist in compiled code
			
		if ci is None and self._namespace is not None:
			fi.name = f'{self._namespace}::{fi.name}'
		if fi.is_static:
			if fi.mangled_name in self.function_defs:
				raise Exception(f'Duplicate function def {fi.name} {fi.mangled_name}')
			self.function_defs[fi.mangled_name] = fi
		else:
			assert ci is not None
			ci.add_method(fi)

	def collect(self, node: Cursor):
		# Should we even inspect this one?
		usr = node.get_usr() # Unified Symbol Resolution
		if usr in self._seen_usrs:
			return
		elif node.kind in (CursorKind.STRUCT_DECL, CursorKind.UNION_DECL, CursorKind.ENUM_DECL) and not node.is_definition():
			# Ignore forward declaractions. They have the same USR as the definition, but may be in a different file.
			return
		elif len(usr) != 0 and not node.kind == CursorKind.NAMESPACE:
			self._seen_usrs.add(usr)

		# Do we collect this one?
		project_file = is_in_project_file(node)
		if node.kind in collectable_type_declarations:
			if project_file:
				self.collect_type(node.type)
		elif node.kind == CursorKind.FUNCTION_DECL:
			if project_file or node.mangled_name in self._known_symbols:
				self.collect_function_info(node)
		elif node.kind == CursorKind.VAR_DECL:
			if project_file or node.mangled_name in self._known_symbols:
				self.collect_var_or_field(node)
		elif node.kind == CursorKind.CLASS_TEMPLATE:
			if project_file:
				self._class_template_cursors[node.spelling] = node
				#print(f'Templates not yet fully supported. {node.spelling}')
		elif node.kind == CursorKind.FUNCTION_TEMPLATE:
			pass
		else:
			# collect child cursors
			old_namespace = self._namespace
			if node.kind == CursorKind.NAMESPACE:
				self._namespace = node.spelling if old_namespace is None else f'{old_namespace}::{node.spelling}'
			for c in node.get_children():
				self.collect(c)
			self._namespace = old_namespace

def get_translation_unit(path: str, clang_args: list) -> TranslationUnit:
	arm_root = os.environ.get('NDS-SRE-ARM-ROOT')
	assert arm_root is not None and Path(arm_root).exists(), f'Environment variable NDS-SRE-ARM-ROOT must be set to an existing directory (is {arm_root})'
	
	language = 'c'
	if path.endswith('pp'):
		language = 'c++'
	
	index = Index.create()
	all_args = ([]
		# flags from NCPatcher
		+ '-mcpu=arm946e-s -mno-unaligned-access -mfloat-abi=soft -mabi=aapcs'.split(' ')
		+ '-Os -fno-short-enums -fomit-frame-pointer -ffast-math -fno-builtin -nostdlib -nodefaultlibs -DSDK_FINALROM'.split(' ')
		+ '-fno-rtti -fno-exceptions'.split(' ')
		+ [
		'-DSDK_ARM9', # This isn't in the .json file given in the NSMB template for NCPatcher, but seems necessary. Does NCPatcher automatically include it?
		'-x', language,
		'-target', 'arm-none-eabi',
		'-fsyntax-only',
		'-fpack-struct=4', # Align 8-byte ints as 4 bytes
		'-Wno-pragma-once-outside-header', # We'll directly parse a header, clang will see it is in the main file and thus assume it is 'outside-header'
		# our includes
		f'-I{project_include_path}',
		# clang includes
		f'--sysroot={arm_root}/lib/clang-runtimes/arm-none-eabi/armv5te',
		f'-resource-dir={arm_root}/lib/clang/18',
	] + clang_args)
	return index.parse(path, args=all_args)

def parse_project(
 header_file: str,
 clang_args: list[str],
 known_symbols: Container[str] | None = None,
 return_errors: bool = False) -> ParseResults | list[str]:
	# must use absolute for project_include_path and because we can't get parent of '.'
	file_to_parse = Path(header_file).absolute()
	assert file_to_parse.exists()
	
	global project_include_path
	project_include_path = str(file_to_parse.parent).replace('\\', '/')
		
	# scan, collect types
	tu = get_translation_unit(header_file, clang_args)
	errors = []
	for diag in tu.diagnostics:
		# Weird.
		diag_str = str(diag)
		if diag.severity > 2:
			errors.append(diag_str)
		elif not return_errors:
			print(diag_str)
	
	if return_errors:
		return errors
	elif len(errors) > 0:
		raise Exception(f'libclang error(s):\n' + str.join('\n', errors))
	
	results = ParseResults(tu, known_symbols or set())
	
	return results
