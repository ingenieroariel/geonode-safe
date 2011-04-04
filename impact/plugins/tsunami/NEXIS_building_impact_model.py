
import numpy
import scipy

from riab_server.function.plugins import FunctionProvider
from django.template.loader import render_to_string
from riab_server.core.utilities import MAXFLOAT
from damage_curve import Damage_curve



#------------------------------------------------------------
# Define damage curves for tsunami structural building damage
#------------------------------------------------------------
struct_damage_curve = {'Double brick': Damage_curve([[-MAXFLOAT, 0.0],
                                                     [0.0, 0.016],
                                                     [0.1, 0.150],
                                                     [0.3, 0.425],
                                                     [0.5, 0.449],
                                                     [1.0, 0.572],
                                                     [1.5, 0.582],
                                                     [2.0, 0.587],
                                                     [2.5, 0.647],
                                                     [MAXFLOAT, 64.7]]),
                       'Brick veneer': Damage_curve([[-MAXFLOAT, 0.0],
                                                     [0.0, 0.016],
                                                     [0.1, 0.169],
                                                     [0.3, 0.445],
                                                     [0.5, 0.472],
                                                     [1.0, 0.618],
                                                     [1.5, 0.629],
                                                     [2.0, 0.633],
                                                     [2.5, 0.694],
                                                     [MAXFLOAT, 69.4]]),
                       'Timber': Damage_curve([[-MAXFLOAT, 0.0],
                                               [0.0, 0.016],
                                               [0.3, 0.645],
                                               [1.0, 0.818],
                                               [2.0, 0.955],
                                               [MAXFLOAT, 99.4]])}

contents_damage_curve = Damage_curve([[-MAXFLOAT, 0.0],
                                      [0.0, 0.013],
                                      [0.1, 0.102],
                                      [0.3, 0.381],
                                      [0.5, 0.500],
                                      [1.0, 0.970],
                                      [1.5, 0.976],
                                      [2.0, 0.986],
                                      [MAXFLOAT, 98.6]])


class TsunamiBuildingLossFunction(FunctionProvider):
    """Risk plugin for earthquake damage based on empirical results

    :param requires category=="hazard" and subcategory.startswith("tsunami") and layerType=="raster"
    :param requires category=="exposure" and subcategory.startswith("building") and layerType=="feature"
    """

    @staticmethod
    def run(hazard_layers, exposure_layers):
        """Risk plugin for tsunami building damage
        """

        coordinates, inundation = hazard_layers
        coordinates, buildings = exposure_layers

        N = len(buildings)

        impact = []
        for i in range(N):

            #-------------------
            # Extract parameters
            #-------------------
            depth = float(inundation[i]
                          ['tsunami_max_inundation_depth_BB_geographic_nan0'])
            shore_distance = float(buildings[i]['SHORE_DIST'])
            wall_type = str(buildings[i]['WALL_TYPE'])
            number_of_people_in_building = int(buildings[i]['NEXIS_PEOP'])
            contents_value = float(buildings[i]['CONT_VALUE'])
            structure_value = float(buildings[i]['STR_VALUE'])

            #------------------------
            # Compute people affected
            #------------------------
            if 0.01 < depth < 1.0:
                people_affected = number_of_people_in_building
            else:
                people_affected = 0

            if depth >= 1.0:
                people_severely_affected = number_of_people_in_building
            else:
                people_severely_affected = 0

            #----------------------------------------
            # Compute impact on buldings and contents
            #----------------------------------------
            depth_floor = depth - 0.3  # Adjust for floor height

            if depth_floor >= 0.0:
                buildings_inundated = 1
            else:
                buildings_inundated = 0

            if depth_floor < 0.0:
                structural_damage = contents_damage = 0.0
            else:
                # Water is deep enough to cause damage
                if wall_type in struct_damage_curve:
                    curve = struct_damage_curve[wall_type]
                else:
                    # Establish default for unknown wall type
                    curve = struct_damage_curve['Brick veneer']

                structural_damage = curve(depth_floor)
                contents_damage = contents_damage_curve(depth_floor)

            #---------------
            # Compute losses
            #---------------
            structural_loss = structural_damage * structure_value
            contents_loss = contents_damage * contents_value

            #-------
            # Return
            #-------
            impact.append({'NEXIS_PEOP': number_of_people_in_building,
                           'PEOPLE_AFFECTED': people_affected,
                           'PEOPLE_SEV_AFFECTED': people_severely_affected,
                           'STRUCT_INUNDATED': buildings_inundated,
                           'STRUCT_DAMAGE_fraction': structural_damage,
                           'CONTENTS_DAMAGE_fraction': contents_damage,
                           'STRUCT_LOSS_AUD': structural_loss,
                           'CONTENTS_LOSS_AUD': contents_loss,
                           'DEPTH': depth})

        return impact