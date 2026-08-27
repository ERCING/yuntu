import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np


color_dtype = np.dtype([('Temperature', 'float'), ('Color', 'U7')])
color_map = {'IR-BD':np.array([(-100, '#555555'), (-81.01, '#555555'), (-81, '#878787'), (-76.01, '#878787'), (-76, '#FFFFFF'), (-70.01, '#FFFFFF'),
                               (-70, '#000000'), (-64.01, '#000000'), (-64, '#A0A0A0'), (-53.01, '#A0A0A0'), (-53, '#6E6E6E'), (-42.01, '#6E6E6E'),
                               (-42, '#3C3C3C'), (-31.01, '#3C3C3C'), (-31, '#e0e0e0'), (8.99, '#6b6b6b'), (9, '#FFFFFF'), (30, '#000000'),
                               (40, '#000000')], dtype=color_dtype),
             'IR-CC':np.array([(-100, "#FFFFFF"), (-85.01, "#FFFFFF"), (-85, "#000096"), (-81.01, "#000096"), (-81, "#4169E1"), (-76.01, "#4169E1"),
                               (-76, "#00BFFF"), (-70.01, "#00BFFF"), (-70, '#A0D2FF'), (-64.01, '#A0D2FF'), (-64, '#FFE132'), (-53.01, '#FFE132'),
                               (-53, "#FF6E00"), (-42.01, "#FF6E00"), (-42, "#A02323"), (-31.01, "#A02323"), (-31, "#FFFFFF"), (8.99, '#4A2525'),
                               (9, '#FFFFFF'), (30, '#000000'), (40, '#000000')], dtype=color_dtype),
             'IR-CA':np.array([(-100, '#FFFFFF'), (-90, '#CBCBFF'), (-84.5, '#5639B4'), (-76, '#C62723'), (-64, '#F8A400'), (-58.5, '#E8ED00'),
                               (-50, '#5BE924'), (-40, '#16BC71'), (-20, '#12607F'), (8.999, '#0C334C'), (9, '#5D5E5E'), (30, '#000000'), (40, '#000000'), (50, '#880000')
                               ], dtype=color_dtype),
             'IR-OTT':np.array([(-100, '#FFFFFF'), (-90.01, '#FFFFFF'), (-90, '#7D007A'), (-80.01, '#E664BC'), (-80, '#D7E1DA'), (-70, '#000000'),
                                (-60, '#FF0000'), (-50, '#FFFF00'), (-40, '#00FF00'), (-30, '#000F6C'), (-20.01, '#00FFFF'), (-20, '#D4C2C2'),
                                (30, '#000000'), (40, '#000000')], dtype=color_dtype),
             'IR-RAMMB':np.array([(-100, '#000000'), (-90.01, '#FFFFFF'), (-90, '#000000'), (-80.01, '#FFFF00'), (-80, '#FF0000'), (-70.01, '#640000'),
                                  (-70, '#00FF00'), (-60.01, '#006400'), (-60, '#0000FF'), (-50.01, '#000064'), (-50, '#5A5A5A'), (-40, '#85AAAA'),
                                  (-30.01, '#B4FFFF'), (-30, '#FFFFFF'), (30, '#000000'), (40, '#000000')], dtype=color_dtype),
             'IR-RBTOP':np.array([(-100, '#FFFFFF'), (-75, '#000000'), (-65.01, '#DA0000'), (-65, '#FF0000'), (-55.01, '#FFDA00'), (-55, '#FFFF00'),
                                  (-45, '#00FF00'), (-25, '#0000FF'), (-20, '#BF00FF'), (-15, '#FFFFFF'), (25, '#000000'), (25.01, '#AAAAAA'),
                                  (50, '#000000')], dtype=color_dtype),
             'IR-WK':np.array([(-100, '#00FAF4'), (-90, '#9D00FF'), (-80, '#CE00FF'), (-75, '#FE6060'), (-70, '#FE8F20'),
                               (-65, '#FCC140'), (-60, '#FEE674'), (-53, '#FEFECC'), (-42, '#00FAF4'), (-31, '#5EBAFF'),
                               (-11, '#2F6EA1'), (9, '#002244'), (30, '#000000'), (40, '#000000')], dtype=color_dtype),
             'WV': np.array([(-100, '#800000'), (-70, '#800000'), (-40, '#FFFF80'), (-35, '#80FF80'), (-28, '#80FFFF'), (-10, '#1D61D3'),
                                (0, '#621161'), (0.01, '#FFFFFF'), (40, '#FFFFFF')], dtype=color_dtype),
             'WV-SSD':np.array([(-100, '#00FFFF'), (-74, '#006F00'), (-47, '#FFFFFF'), (-30, '#0000AB'), (-14, '#FDFD00'), (0, '#FF0000'),
                               (0.01, '#000000')], dtype=color_dtype),
             'VIS-GRAY':np.array([(0, '#000000'), (25, '#666666'), (50, '#999999'), (75, '#CCCCCC'), (100, '#FFFFFF')], dtype=color_dtype),
             'VIS-ENH':np.array([(0, '#000000'), (15, '#224488'), (30, '#4488CC'), (45, '#88CCFF'), (60, '#FFFFFF'),
                                  (75, '#FFFFCC'), (90, '#FFCC88'), (100, '#FFFFFF')], dtype=color_dtype)}


def my_color_map(name: str):
    data = color_map[name]
    temps = data["Temperature"]
    hex_colors = data["Color"]
    norm = mcolors.Normalize(vmin=temps.min(), vmax=temps.max())
    cmap = mcolors.LinearSegmentedColormap.from_list(
        name, list(zip(norm(temps), hex_colors))
    )
    return cmap, norm