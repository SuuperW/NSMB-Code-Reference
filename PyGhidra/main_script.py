# Generate programs for NSMB

#@category NDS-SRE
#@runtime PyGhidra

OPTION_DELETE_ON_ERROR = True

if int(getGhidraVersion()[:2]) < 12:
	raise Exception('Ghidra versions before 12 are not supported.')

from pathlib import Path
import importlib.util
import os
import sys

import ImportNDS
import header_parser
import parse_symbols_file
import import_libclang

from ghidra.app.services import ProgramManager
from ghidra.framework.model import DomainFile
from ghidra.program.model.data import DataTypeManager
from ghidra.program.database import DataTypeArchiveDB
from ghidra.program.model.listing import Program

locking_object = ''
type_archive_name = 'ProjectTypes'

class ProgramGenerator:
	project_archive: DataTypeArchiveDB | None
	project_archive_file: DomainFile | None
	project_type_manager: DataTypeManager
	tm_tid: int
	
	project_root: str
	config: dict
	parse_results: header_parser.ParseResults
	symbols_arm9: dict
	
	program: Program | None
	prog_tid: int
	all_programs: list[Program]
	
	_has_reported_symbols: bool
	_has_released: bool
	_rom_data_path: str
	
	def __init__(self, project_root: str, config: dict):
		self.program = None
		self.all_programs = []
		
		self.project_root = project_root
		
		project_folder = getProjectRootFolder()
		paf = project_folder.getFile(type_archive_name)
		if paf is not None:
			self.project_archive = paf.getDomainObject(locking_object, False, False, monitor)
		else:
			self.project_archive = DataTypeArchiveDB(project_folder, type_archive_name, locking_object)
		self.project_archive_file = paf
		self.project_type_manager = self.project_archive.getDataTypeManager()
		
		self.tm_tid = self.project_type_manager.startTransaction('')
		self._has_released = False
		
		if 'programs' not in config:
			config['programs'] = {}
		if len(config['programs']) == 0:
			proj_name = project_root.replace('\\', '/').split('/')[-1]
			config['programs'][proj_name] = {}
		if 'c_types_to_ignore' not in config:
			config['c_types_to_ignore'] = []
		self.config = config
		self._has_reported_symbols = False
		
		if Path(f'{self.project_root}/ghidra_files/ghidraData.bin').exists():
			self._rom_data_path = f'{self.project_root}/ghidra_files/ghidraData.bin'
		elif Path(f'{self.project_root}/files/ghidraData.bin').exists():
			self._rom_data_path = f'{self.project_root}/files/ghidraData.bin'
		else:
			raise Exception('ghidraData.bin was not found under [project]/files or [project]/ghidra_files')
		print(self._rom_data_path)
	
	def generate_types(self):
		type_generator = import_libclang.TypeGenerator(this, self.project_type_manager)
		type_generator.generate(self.parse_results, self.config['c_types_to_ignore'])
	
	def create_program(self, name: str, program_config: dict):
		ImportNDS.join(this)
		importer = ImportNDS.ROM_Importer(this, self._rom_data_path, name, program_config)
		self.program = importer.program
		self.all_programs.append(self.program)
		self.prog_tid = self.program.startTransaction('', None)
		importer.loadRomCode()
		
		report_symbols = (not self._has_reported_symbols) and (not program_config['skip_unloaded_overlays'])
		
		symbol_generator = import_libclang.SymbolGenerator(currentProgram, self.project_type_manager)	
		symbol_generator.generate(
			self.parse_results,
			self.symbols_arm9,
			importer.overlay_spaces,
			report_symbols,
		)
		if report_symbols:
			self._has_reported_symbols = True
		
		self.program.endTransaction(self.prog_tid, True)
		self.program = None
	
	def generate(self):
		print('parsing header files...')
		self.parse_results = header_parser.parse_project(self.project_root, [])
		print('parsing symbols...')
		self.symbols_arm9 = parse_symbols_file.parse_symbols(f'{self.project_root}/symbols9.x')	
		print('creating Ghidra types...')		
		self.generate_types()
		
		programs = self.config['programs']
		for program_name in programs:
			print(f'creating program "{program_name}"')
			self.create_program(program_name, programs[program_name])
		
		self.release(True)
	
	def release(self, save: bool):
		if self._has_released:
			return
		assert self.project_archive is not None
		
		self.project_type_manager.endTransaction(self.tm_tid, save)
		if self.program is not None:
			self.program.endTransaction(self.prog_tid, save)
			
		if save:
			self.project_archive.save('', monitor)
		self.project_archive.release(locking_object)
		self.project_archive = None # Once released, it is closed and the object cannot be used.
		if (not save) and self.project_archive_file is None:
			# The file did not exist before starting generation, so delete it
			paf = getProjectRootFolder().getFile(type_archive_name)
			paf.delete()
		
		self._has_released = True

if __name__ == '__main__':
	project_root = os.environ.get('GHIDRA_EXTRACT_SOURCE')
	if project_root is None:
		project_root = askDirectory('source location', 'load').getAbsolutePath()
	assert Path(project_root).is_dir(), f'The given source directory {project_root} does not exist. '
	
	config = None
	has_config = False
	config_path = f'{project_root}/ghidra_files/config.py'
	if Path(config_path).exists:
		spec = importlib.util.spec_from_file_location('config', config_path)
		config = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(config)
		assert hasattr(config, 'config')
		config = config.config
		has_config = True
	else:
		config = {}
		print('No config file found. Using defaults.')

	program_manager = state.getTool().getService(ProgramManager)
	g = ProgramGenerator(project_root, config)
	finished = False
	try:
		g.generate()
		finished = True
	finally:
		should_delete = (not finished) and OPTION_DELETE_ON_ERROR
		g.release(not should_delete)
		if should_delete:
			# delete all generated programs
			for p in g.all_programs:
				program_manager.closeProgram(p, True)
