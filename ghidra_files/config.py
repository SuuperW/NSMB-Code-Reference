config = {
	'programs': {
		# name of Ghidra program to create
		'NSMB (in level)': {
			# These overlays will be put in RAM space instead of an overlay space.
			# This means Ghidra will see references to their addresses as references to what's in these overlays.
			# These particular overlays are always loaded while playing a level.
			'loaded_overlays': [0, 10, 11, 54 ],
			# If this is true, overlays who's addresses overlap a loaded overlay will not be included in the program.
			'skip_unloaded_overlays': False,
			# Group multiple overlays into the same address space.
			# This means Ghidra will assume references from one to address(s) in another as references to that other overlay. A group cannot contain overlays that overlap with each other.
			'overlay_groups': {
				# name:  [ overlay IDs ]
				'ov_g1': [40, 49], # Overlay 40 contains a reference to overlay 49.
				'ov_g2': [96, 107], # These pairs aren't necessarily always loaded together, though.
			},
		},
	},
	'c_types_to_ignore': ['BitFlag<u32>', 'BitFlag<u8>', 'StrongBitFlag<u32>']
}

# We can probably make do with just the one program above, but you could use these too.
# It's likely another would be good for looking at minigames, but I have not looked at that.
example_programs = {
	'NSMB': {
		# nothing here, so defaults are used; all overlays are included with their own overlay space
	},
	'overworld': {
		'loaded_overlays': [0, 8, 11, 54 ],
		'skip_unloaded_overlays': True,
	}
}

# overlays grouped by address ranges:
#   1- 10
#  11- 11
#  12- 21
#  22- 31
#  32- 41
#  42- 51
#  55- 65
#  66- 75
#  76- 85
#  86- 95
#  96-105
# 106-115
# 116-125
