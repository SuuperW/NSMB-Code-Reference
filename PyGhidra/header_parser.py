from __future__ import annotations
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
	renamed_type: Type
	new_name: str
	old_name: str

	def __init__(self, new_name, renamed_type, old_name):
		self.new_name = new_name
		self.renamed_type = renamed_type
		self.old_name = old_name

class FunctionInfo:
	clang_type: Type
	
	name: str
	mangled_name: str
	
	is_thiscall: bool
	is_static: bool
	is_virtual: bool
	is_ctor: bool
	is_dtor: bool
	is_maybe_inline: bool
	is_consteval: bool
	
	class_member: bool
	
	param_names: list[str]
	
	def __init__(self, class_name: str | None, node: Cursor):
		assert node.kind in (CursorKind.CXX_METHOD, CursorKind.CONSTRUCTOR, CursorKind.DESTRUCTOR, CursorKind.FUNCTION_DECL, CursorKind.CONVERSION_FUNCTION), node.kind
		
		self.clang_type = node.type
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

		self.param_names = []
		for arg in node.get_arguments():
			self.param_names.append(arg.spelling)

	def get_signature_with_name(self):
		"""Replaces destructor name with just a ~, so that signature can be compared with base class"""
		sig = self.clang_type.spelling.replace(' noexcept', '')
		index = sig.index('(')
		if '~' in self.name:
			return f'{sig[:index]}~{sig[index:]}'
		return f'{sig[:index]}{self.name.split('::')[-1]}{sig[index:]}'

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
def is_project_file(path: str) -> bool:
	# Using pathlib to more properly check paths is very slow (since we'll be doing this many thousands of times)
	# This works.
	# It use to work without doing this replace. But at some point the paths I got from clang Cursor.location started including a mix of / and \ (even ignoring everything up to /include/) ... weird.
	path = path.replace('\\', '/')
	return path.startswith(project_include_path)
def is_in_project_file(cursor: Cursor) -> bool:
	loc = cursor.location
	if bool(loc.file):
		fname = str(loc.file.name)
		return is_project_file(fname)
	return False

path_map = {}
def get_full_path(path: str):
	mapped = path_map.get(path)
	if mapped is None:
		mapped = str(Path(path).resolve()) # stats file; slow
		path_map[path] = mapped
	return mapped
def get_node_file(node: Cursor):
	return get_full_path(str(node.location.file))

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
		print(clang_type.get_declaration(), clang_type.get_declaration().get_usr())
		raise Exception('attempted to get the name of a member pointer; only the typedef has a name')
		
	elif clang_type.kind == TypeKind.LVALUEREFERENCE:
		return get_friendly_name(clang_type.get_pointee())
	
	tag = None
	if clang_type.is_pod(): # some types above are "plain old data"
		tag = clang_type.spelling
	elif clang_type.kind == TypeKind.ENUM:
		tag = clang_type.spelling.replace('enum ', '')
	elif is_class_type(clang_type):
		tag = clang_type.spelling.replace('struct ', '').replace('union ', '')
	if tag is not None:
		if 'anonymous ' in tag:
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

# --- Collection
def get_typedef_info(typedef: Cursor) -> TypedefInfo | Type:
	name = get_friendly_name(typedef.type)
	underlying = unelaborate(typedef.underlying_typedef_type)
	underlying_name = None 
	if underlying.kind != TypeKind.MEMBERPOINTER:
		# If it is a member pointer, we won't ever access old_name.
		underlying_name = get_friendly_name(underlying)
	
	if name != underlying_name:
		return TypedefInfo(name, underlying, underlying_name)

	if underlying.kind in (TypeKind.RECORD, TypeKind.ENUM):
		return underlying # this happens for typedef struct Foo {} Foo, since we remove 'struct '
	else:
		raise Exception(f'Unexpected same-name typedef {name} = {underlying.spelling}, {underlying.kind}')

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
	
	_unsupported_messages: set[str]
	
	def __init__(self, tu: TranslationUnit):
		self.classes = {}
		self.typedefs = {}
		self.enums = {}
		self.function_member_pointers = {}
		self.function_defs = {}
		self.static_vars = {}
		
		self._namespace = None
		self._seen_usrs = set()
		self._collected_type_decls = set()
		
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

	def collect_type_members(self, node: Type):
		node = unelaborate(node)
		ci = ClassInfo(node)
		
		if node.kind == TypeKind.UNEXPOSED and node.get_num_template_arguments() > 0 and node.get_size() < 0:
			self._incomplete_template_instances[ci.name] = node
			return
		
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
					fi = FunctionInfo(ci.name, child)
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
	
	def collect_func_referenced_types(self, func_type: Type):
		# For these, the type might again be a function pointer.
		# So, add param to collect_type to allow it and make up a name?
		# That function's parameters might also include a function type!
		if func_type.get_result() != TypeKind.VOID:
			self.collect_type(func_type.get_result())
		for arg_type in func_type.argument_types():
			self.collect_type(arg_type)
	
	def collect_type_ti(self, ti: TypedefInfo):
		if ti.renamed_type.kind != TypeKind.MEMBERPOINTER:
			assert ti.new_name not in self.typedefs, f'Duplicate typedef {ti.new_name}'
			self.typedefs[ti.new_name] = ti
			base_renamed = get_base_type(ti.renamed_type)
			if base_renamed.kind != TypeKind.FUNCTIONPROTO:
				self.collect_type(base_renamed)
			else:
				self.collect_func_referenced_types(base_renamed)
		else:
			assert ti.new_name not in self.function_member_pointers, f'Duplicate member pointer {ti.new_name}'
			self.function_member_pointers[ti.new_name] = ti.renamed_type
			self.collect_func_referenced_types(ti.renamed_type.get_pointee())
	
	def is_already_collected(self, clang_type: Type) -> bool:
		# We can mostly rely on Unified Symbol Resolution to distinguish between types.
		# But this fails with anonymous types. Multiple anonymous types within a struct have the same USR.
		# So we also use Cursor.hash.
		# Cursor.hash cannot be used alone because different template instantiations have the same declaration cursor.
		# But also we cannot include the hash for non-anonymous types because certain typedefs do get defined twice, with different cursors. (e.g. size_t in the standard library)
		
		type_decl = clang_type.get_declaration()
		if clang_type.kind == TypeKind.UNEXPOSED and type_decl.kind == CursorKind.NO_DECL_FOUND:
			# https://github.com/llvm/llvm-project/issues/192268
			clang_type = clang_type.get_canonical()
			type_decl = clang_type.get_declaration()
		
		if clang_type.kind.value < TypeKind.COMPLEX.value and clang_type.kind.value >= TypeKind.VOID.value:
			return True # built-in type
		
		maybe_hash = type_decl.hash if 'anonymous ' in clang_type.spelling else 0
		usr_hash = (str(type_decl.get_usr()), maybe_hash)
		if usr_hash in self._collected_type_decls:
			return True
		
		self._collected_type_decls.add(usr_hash)
		return False
		
	def collect_type(self, node: Type):	
		node = get_base_type(node)
		#if len(usr) == 0 and node.kind.value >= TypeKind.COMPLEX.value: # not built-in type
		#	raise Exception(f'Cannot collect type with no USR: {node.spelling} {node.kind}')
		if self.is_already_collected(node):
			return
		
		if node.kind == TypeKind.TYPEDEF:
			ti = get_typedef_info(node.get_declaration())
			if isinstance(ti, TypedefInfo):
				self.collect_type_ti(ti)
			else:
				self.collect_type(ti)
		# struct/union/class
		elif is_class_type(node):
			self.collect_type_members(node)
		# enum
		elif node.kind == TypeKind.ENUM:
			enum_name = get_friendly_name(node)
			assert enum_name not in self.enums, f'Duplicate enum {enum_name}'
			self.enums[enum_name] = node
		
		elif node.kind in (TypeKind.FUNCTIONPROTO, TypeKind.FUNCTIONNOPROTO, TypeKind.MEMBERPOINTER) or not node.is_pod():
			raise Exception(f'Cannot collect type {node.spelling} {node.kind}')
	
	def collect_var_or_field(self, var_decl: Cursor, class_name: str | None = None):
		collect_type = True
		if get_base_type(var_decl.type).kind == TypeKind.FUNCTIONPROTO:
			func_name = self.append_namespace(f'{var_decl.spelling}_func', class_name)
			self.collect_type_ti(TypedefInfo(func_name, var_decl.type, 'code*'))
			collect_type = False
		
		# field
		if var_decl.kind == CursorKind.FIELD_DECL:
			if collect_type:
				self.collect_type(var_decl.type)
			return
		
		# var
		if collect_type:
			self.collect_type(var_decl.type)
		var_name = self.append_namespace(var_decl.spelling, class_name)
		vi = VarInfo(var_name, var_decl, class_name is not None)
		if vi.mangled_name in self.static_vars:
			raise Exception(f'Duplicate var {vi.name} {vi.mangled_name} {var_decl.location}')
		self.static_vars[vi.mangled_name] = vi

	def collect_function_info(self, node: Cursor, ci: ClassInfo | None = None):
		class_name = None if ci is None else ci.name
		fi = FunctionInfo(class_name, node)
		if fi.is_consteval:
			return # the function won't exist in compiled code
			
		if ci is None and self._namespace is not None:
			fi.name = f'{self._namespace}::{fi.name}'
		self.collect_func_referenced_types(fi.clang_type)
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
			if project_file:
				self.collect_function_info(node)
		elif node.kind == CursorKind.VAR_DECL:
			if project_file:
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

def get_translation_unit(path: str, project_root: str, clang_args: list, return_errors: bool = False) -> TranslationUnit:
	index = Index.create()
	all_args = ([]
		# flags from NCPatcher
		+ '-mcpu=arm946e-s -mno-unaligned-access -mfloat-abi=soft -mabi=aapcs'.split(' ')
		+ '-Os -fno-short-enums -fomit-frame-pointer -ffast-math -fno-builtin -nostdlib -nodefaultlibs -DSDK_GCC -DSDK_FINALROM'.split(' ')
		+ '-fno-rtti -fno-exceptions -std=c++23'.split(' ')
		+ [
		'-DSDK_ARM9', # This isn't in the .json file given in the NSMB template for NCPatcher, but seems necessary. Does NCPatcher automatically include it?
		'-x', 'c++', # language
		'-target', 'arm-none-eabi',
		'-fsyntax-only',
		'-fpack-struct=4', # Align 8-byte ints as 4 bytes
		'-Wno-pragma-once-outside-header', # We'll directly parse a header, clang will see it is in the main file and thus assume it is 'outside-header'
		# our includes
		f'-I{project_root}/include',
		f'-I{project_root}/nitro_include',
		# clang includes
		f'--sysroot={project_root}/LLVM-ET-Arm/lib/clang-runtimes/arm-none-eabi/armv5te',
		f'-resource-dir={project_root}/LLVM-ET-Arm/lib/clang/18',
	] + clang_args)
	return index.parse(path, args=all_args)

def parse_project(
 project_root: str,
 clang_args: list[str],
 return_errors: bool = False) -> ParseResults | list[str]:
	global project_include_path
	project_include_path = project_root.replace('\\', '/') + '/include/'
		
	# scan, collect types
	file_to_parse = (Path(project_root) / 'ghidra_files'/ 'for_ghidra.h').absolute()
	assert file_to_parse.exists()
	tu = get_translation_unit(str(file_to_parse), project_root, [])
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
	
	results = ParseResults(tu)
	
	return results
