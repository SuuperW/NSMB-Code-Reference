ram_groups = {
	'level': [0, 10, 11, 54 ],
	'overworld': [0, 8, 11, 54 ],
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

# These two overlays seem to have anomalous references (pointers to overlay addresses not contained in a "ram_group" above)
# Maybe at some point something will be done for them.
#40: [42, 43, 46, 47, 48, 49, 50,]
#96: [55, 106, 107, 108, 109, 110, 111,]
