"""
SAFE HTTP API

All API calls start with:
 /safe/api/v1

 * Version: All API calls begin with API version.
 * Path: For this documentation, we will assume every
         request begins with the above path.
 * Units: All coordinates are in WGS-84 (EPSG:4326)
          unless otherwise specified and all units of
          measurement are in the International System
          of Units (SI).
 * Format: All calls are returned in JSON.
 * Status Codes:
    200 Successful GET and PUT.
    201 Successful POST.
    202 Successful calculation queued.
    204 Successful DELETE
    401 Unauthenticated.
    409 Unsuccessful POST, PUT, or DELETE
        (Will return an errors object).
"""
from __future__ import division

import sys
import inspect
import datetime

from geonode_safe.storage import download
from geonode_safe.storage import get_metadata
from geonode_safe.storage import save_file_to_geonode
from geonode_safe.models import Calculation, Workspace
from geonode_safe.utilities import bboxlist2string
from geonode_safe.utilities import titelize
from geonode_safe.utilities import get_common_resolution, get_bounding_boxes

from safe.api import get_admissible_plugins
from safe.api import calculate_impact

from geonode.layers.utils import get_valid_user

from django.utils import simplejson as json
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page

from urlparse import urljoin


def exception_format(e):
    """Convert an exception object into a string,
    complete with stack trace info, suitable for display.
    """
    import traceback
    info = ''.join(traceback.format_tb(sys.exc_info()[2]))
    return str(e) + '\n\n' + info


def get_servers(user):
    """ Gets the list of servers for a given user
    """
    if user.is_anonymous():
        theuser = get_valid_user()
    else:
        theuser = user

    servers = []

    try:
        workspace = Workspace.objects.get(user=theuser)
        servers = workspace.servers.all()
    except Workspace.DoesNotExist:
        # It is okay to not load workspaces,
        # the default geoserver is being defined below.
        pass

    geoservers = [{'url': settings.GEOSERVER_BASE_URL + 'ows',
                   'name': 'Local Geoserver',
                   'version': '1.0.0', 'id':0}]
    for server in servers:
        # TODO for the moment assume version 1.0.0
        geoservers.append({'url': server.url,
                           'name': server.name,
                           'id': server.id,
                           'version': '1.0.0'})

    return geoservers


@csrf_exempt
def calculate(request, save_output=save_file_to_geonode):
    start = datetime.datetime.now()

    if request.method == 'GET':
        # FIXME: Add a basic form here to be able to generate the POST request.
        return HttpResponse('This should be accessed by robots, not humans.'
                            'In other words using HTTP POST instead of GET.')
    elif request.method == 'POST':
        data = request.POST
        impact_function_name = data['impact_function']
        hazard_server = data['hazard_server']
        hazard_layer = data['hazard']
        exposure_server = data['exposure_server']
        exposure_layer = data['exposure']
        requested_bbox = data['bbox']
        keywords = data['keywords']

    if request.user.is_anonymous():
        theuser = get_valid_user()
    else:
        theuser = request.user

    # Create entry in database
    calculation = Calculation(user=theuser,
                              run_date=start,
                              hazard_server=hazard_server,
                              hazard_layer=hazard_layer,
                              exposure_server=exposure_server,
                              exposure_layer=exposure_layer,
                              impact_function=impact_function_name,
                              success=False)

    # Wrap main computation loop in try except to catch and present
    # messages and stack traces in the application
    try:
        # Get metadata
        haz_metadata = get_metadata(hazard_server, hazard_layer)
        exp_metadata = get_metadata(exposure_server, exposure_layer)

        # Determine common resolution in case of raster layers
        raster_resolution = get_common_resolution(haz_metadata, exp_metadata)

        # Get reconciled bounding boxes
        haz_bbox, exp_bbox, imp_bbox = get_bounding_boxes(haz_metadata,
                                                          exp_metadata,
                                                          requested_bbox)

        # Record layers to download
        download_layers = [(hazard_server, hazard_layer, haz_bbox),
                           (exposure_server, exposure_layer, exp_bbox)]

        # Add linked layers if any FIXME: STILL TODO!

        # Get selected impact function
        plugins = get_admissible_plugins()

        msg = ('Could not find "%s" in "%s"' % (
                 impact_function_name, plugins.keys()))
        assert impact_function_name in plugins, msg
  
        impact_function = plugins.get(impact_function_name)
        impact_function_source = inspect.getsource(impact_function)

        # Record information calculation object and save it
        calculation.impact_function_source = impact_function_source

        calculation.bbox = bboxlist2string(imp_bbox)
        calculation.save()

        # Start computation
        msg = 'Performing requested calculation'
        #logger.info(msg)

        # Download selected layer objects
        layers = []
        for server, layer_name, bbox in download_layers:
            msg = ('- Downloading layer %s from %s'
                   % (layer_name, server))
            #logger.info(msg)
            L = download(server, layer_name, bbox, raster_resolution)
            layers.append(L)

        # Calculate result using specified impact function
        msg = ('- Calculating impact using %s' % impact_function_name)
        #logger.info(msg)
        impact_file = calculate_impact(layers=layers,
                                           impact_fcn=impact_function)

        # Upload result to internal GeoServer
        msg = ('- Uploading impact layer %s' % impact_file.name)

        #logger.info(msg)
        result = save_output(impact_file.filename,
                             title='output_%s' % start.isoformat(),
                             user=theuser)
    except Exception, e:
        # FIXME: Reimplement error saving for calculation.
        # FIXME (Ole): Why should we reimplement?
        # This is dangerous. Try to raise an exception
        # e.g. in get_metadata_from_layer. Things will silently fail.
        # See issue #170
        #logger.error(e)
        errors = e.__str__()
        trace = exception_format(e)
        calculation.errors = errors
        calculation.stacktrace = trace
        calculation.save()
        jsondata = json.dumps({'errors': errors, 'stacktrace': trace})
        return HttpResponse(jsondata, mimetype='application/json')

    msg = ('- Result available at %s.' % result.get_absolute_url())
    #logger.info(msg)

    calculation.layer = urljoin(settings.SITEURL, result.get_absolute_url())
    calculation.success = True
    calculation.save()

    output = calculation.__dict__

    # json.dumps does not like datetime objects,
    # let's make it a json string ourselves
    output['run_date'] = 'new Date("%s")' % calculation.run_date

    # FIXME: This should not be needed in an ideal world
    ows_server_url = settings.GEOSERVER_BASE_URL + 'ows',
    output['ows_server_url'] = ows_server_url

    # json.dumps does not like django users
    output['user'] = calculation.user.username
    output['pretty_function_source'] = calculation.pretty_function_source()

    links = result.link_set.all()

    links_dict = {}

    for item in links:
        links_dict[item.name] = {'url': item.url, 
                           'link_type': item.link_type,
                           'extension': item.extension
                          }

    output['links'] = links_dict

    output['caption'] = 'Calculation finished ' \
                            'in %s' % calculation.run_duration

    # Delete _state and _user_cache item from the dict,
    # they were created automatically by Django
    del output['_user_cache']
    del output['_state']

    # If success == True and errors = '' ...
    # ... let's make errors=None for backwards compat
    if output['success'] and len(output['errors']) == 0:
        output['errors'] = None

    jsondata = json.dumps(output)
    return HttpResponse(jsondata, mimetype='application/json')


def debug(request):
    """Show a list of all the functions"""
    plugin_list = get_admissible_plugins()

    plugins_info = []
    for name, f in plugin_list.items():
        if not 'doc' in request.GET:
            plugins_info.append({
             'name': name,
             'location': f.__module__,
            })
        else:
            plugins_info.append({
             'name': name,
             'location': f.__module__,
             'doc': f.__doc__,
            })

    output = {'plugins': plugins_info}
    jsondata = json.dumps(output)
    return HttpResponse(jsondata, mimetype='application/json')


@cache_page(60 * 15)
def questions(request):
    """Get a list of all the questions, layers and functions

       Will provide a list of plugin functions and the layers that
       the plugins will work with. Takes geoserver urls as a GET
       parameter can have a comma separated list

       e.g. http://127.0.0.1:8000/riab/api/v1/functions/?geoservers=http:...
       assumes version 1.0.0
    """

    if 'geoservers' in request.GET:
        # FIXME for the moment assume version 1.0.0
        gs = request.GET['geoservers'].split(',')
        geoservers = [{'url': g, 'version': '1.0.0'} for g in gs]
    else:
        geoservers = get_servers(request.user)

    layers = {}
    functions = {}

    for geoserver in geoservers:
        layers.update(get_metadata(geoserver['url']))

    admissible_plugins = get_admissible_plugins()
    for name, f in admissible_plugins.items():
        functions[name] = {'doc': f.__doc__,
                            } 
        for key in ['author', 'title', 'rating']:
            if hasattr(f, key):
                functions[name][key] = getattr(f, key)

    output = {'layers': layers, 'functions': functions}

    hazards = []
    exposures = []

    # First get the list of all hazards and exposures
    for name, params in layers.items():
        keywords = params['keywords']
        if 'category' in keywords:
            if keywords['category'] == 'hazard':
                hazards.append(name)
            elif keywords['category'] == 'exposure':
                exposures.append(name)

    questions = []

    # Then iterate over hazards and exposures to find 3-tuples of hazard, exposure and functions
    for hazard in hazards:
        for exposure in exposures:
            hazard_keywords = layers[hazard]['keywords']
            exposure_keywords = layers[exposure]['keywords']
            
            hazard_keywords['layertype'] = layers[hazard]['layertype']            
            exposure_keywords['layertype'] = layers[exposure]['layertype']            

            keywords = [hazard_keywords, exposure_keywords]
            plugins = get_admissible_plugins(keywords=keywords)

            for function in plugins:
                questions.append({'hazard': hazard, 'exposure': exposure, 'function': function})

    output['questions'] = questions

    jsondata = json.dumps(output)
    return HttpResponse(jsondata, mimetype='application/json')