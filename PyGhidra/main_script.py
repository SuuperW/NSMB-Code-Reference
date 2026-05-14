# Generate programs for NSMB

#@category NDS-SRE
#@runtime PyGhidra

OPTION_DELETE_ON_ERROR = True

if int(getGhidraVersion()[:2]) < 12:
	raise Exception('Ghidra versions before 12 are not supported.')

from pathlib import Path
import os
import sys

import ImportNDS
import header_parser
import parse_symbols_file
import import_libclang
import programs

from ghidra.app.services import ProgramManager
from ghidra.program.database import DataTypeArchiveDB
from ghidra.program.model.listing import Program

locking_object = ''
type_archive_name = 'NSMB_Types'

class ProgramGenerator:
	program: Program | None
	
	def __init__(self):
		self.program = None
	
	def generate(self, project_root: str):
		print('loading ROM data...')
		ImportNDS.join(this)
		importer = ImportNDS.ROM_Importer(f'{project_root}/files/ghidraData.bin', 'NSMB', [])
		self.program = importer.program
		prog_tid = self.program.startTransaction('', None)
		importer.loadRomCode()
		
		print('parsing header files...')
		parse_results = header_parser.parse_project(project_root, sys.argv[1:])
		
		print('parsing symbols...')
		symbols_arm9 = parse_symbols_file.parse_symbols(this, f'{project_root}/symbols9.x')
		
		# These types from NSMB-CR are problematic for Ghidra. And really they seem totally unnecessary.
		ignore = ['BitFlag<u32>', 'BitFlag<u8>', 'StrongBitFlag<u32>']
		
		print('creating Ghidra types...')
		# Get a project data type archive
		project_folder = getProjectRootFolder()
		project_archive: DataTypeArchiveDB
		paf = project_folder.getFile(type_archive_name)
		if paf is not None:
			project_archive = paf.getDomainObject(project_folder, False, False, monitor)
			project_archive.addConsumer(locking_object)
		else:
			project_archive = DataTypeArchiveDB(project_folder, type_archive_name, locking_object)
		dtm = project_archive.getDataTypeManager()
		# Load the types into it
		tm_tid = dtm.startTransaction('')
		finished = False
		try:
			type_generator = import_libclang.TypeGenerator(this, dtm)
			type_generator.generate(parse_results, ignore)
			symbol_generator = import_libclang.SymbolGenerator(currentProgram, dtm)
			symbol_generator.generate(parse_results, symbols_arm9, importer.overlay_spaces, True)
			finished = True
		finally:
			dtm.endTransaction(tm_tid, True)
			self.program.endTransaction(prog_tid, True)
			if finished or not OPTION_DELETE_ON_ERROR:
				project_archive.save('', monitor)
			project_archive.release(locking_object)
			if OPTION_DELETE_ON_ERROR and not finished:
				# delete the file, if it did not already exist
				if paf is None:
					paf = project_folder.getFile(type_archive_name)
					print(f'deleting {paf}')
					paf.delete()

if __name__ == '__main__':
	project_root = os.environ.get('GHIDRA_EXTRACT_SOURCE')
	if project_root is None:
		project_root = askDirectory('source location', 'load').getAbsolutePath()
	assert Path(project_root).is_dir(), f'The given source directory {project_root} does not exist. '
	
	program_manager = state.getTool().getService(ProgramManager)
	g = ProgramGenerator()
	finished = False
	try:
		g.generate(project_root)
		finished = True
	finally:
		if not finished and OPTION_DELETE_ON_ERROR and g.program is not None:
			program_manager.closeProgram(g.program, True)
