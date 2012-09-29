var layers = undefined;
var functions = undefined;
var questions = undefined;

var hazard_layer = undefined;
var exposure_layer = undefined;

var map = undefined;
var control = undefined;

var result = undefined;

$("#reset").click(function() {
    safe_init();
    map.fitWorld();
    $("#result").css("display", "none"); 
    $("#leftpanel").css("display", "none"); 
    $(".barlittle").css("display", "none");
    $("#answermark").css("display", "none");
    $("#answer").animate({height:"0px"},400);
    $('#functionlist').html('');
    $('#exposurelist').html('');
    $('#hazardlist').html('');
    $(".leaflet-bottom").css("bottom", "70px");
});

function add_hazard_layer(layer_name){
    if (hazard_layer !== undefined){
        map.removeLayer(hazard_layer);
    }

    layer = layers[layer_name];
    hazard_layer = L.tileLayer(layer.tile_url);
    hazard_layer.setOpacity(0.6);
    hazard_layer.addTo(map);

    // Center the map on the extent of the hazard layer
    var bbox = layer.bounding_box;
    var zoom = map.getZoom();
    var bounds = [
        [bbox[1], bbox[0]],
        [bbox[3], bbox[2]]
    ];
    var center = [(bbox[1]+bbox[3])/2, (bbox[0]+ bbox[2])/2];
    map.setView(center, zoom);
    map.fitBounds(bounds);
    control.addOverlay(hazard_layer, 'hazard');
}

function add_exposure_layer(layer_name){
    if (exposure_layer !== undefined){
        map.removeLayer(exposure_layer);
    }

    layer = layers[layer_name];
    exposure_layer = L.tileLayer(layer.tile_url);
    exposure_layer.setOpacity(0.5);
    exposure_layer.addTo(map);
    control.addOverlay(exposure_layer, 'exposure');

}

function calculation_error(data){ 
    $("#result").css("display", "inline");
    $("#leftpanel").css("display", "inline");
    output = "<div class=\"alert alert-error\">" +
                "<a class=\"close\" data-dismiss=\"alert\">×</a>" +
                "<h1>Calculation Failed</h1>" +
                "<p>" + data.errors + "</p></div>";
    $("#result").html(output);
}

function calculate(hazard_name, exposure_name, function_name) {
        var bounds = map.getBounds();
        var minll= bounds.getSouthWest();
        var maxll= bounds.getNorthEast();
        var bbox = ''+minll.lng+','+minll.lat+','+maxll.lng+','+maxll.lat;

        hazard_layer = layers[hazard_name]
        exposure_layer = layers[exposure_name]

        $.ajax({
            type: 'POST',
            url: '/safe/api/v1/calculate/',
            data: {
                hazard_server: hazard_layer.server_url,
                hazard: hazard_name,
                exposure_server: exposure_layer.server_url,
                exposure: exposure_name,
                bbox: bbox,
                keywords: 'safe',
                impact_function: function_name
            },
            success: received,
            error: calculation_error
        });
};

function get_options(items){
    var options = "<option value=\"\">-> Choose one ...</option>";
    for(var key in items){
        if (items.hasOwnProperty(key)){
            option = "<option value='" + key +"'>" +
                 items[key] + "</option>";
            options = options + "\n" + option;
        }
    }
    return options;
};


function showCaption(caption){
    var output = '<div>' + caption + '</div>';
    var resultPanel = $(".result").html(output);
}

function received(data) {
    $(".barlittle").css("display", "none");
    $("#leftpanel").css("display", "inline");
    if (data.errors !== null){
        calculation_error(data);
        return;
    }
    result = data;
    $("#result").css("display", "inline");
    $("#result").addClass('well');
    //$("#result").html(result.caption);
};

function_change = function(r){
    disable_all();
    $("#answer").animate({height:"300px"},400);
    $(".barlittle").css("display", "inline");
    $("#answermark").css("display", "inline");

    $(".leaflet-bottom").css("bottom", "370px");

    hazard_name =  $('#hazardlist option:selected').val();
    exposure_name =  $('#exposurelist option:selected').val();
    function_name =  $('#functionlist option:selected').val();
    calculate(hazard_name, exposure_name, function_name);
};

questions_received = function(r){
    questions = r.questions;
    functions = r.functions;
    layers = r.layers;

    var valid_hazards = {};
    for (i in questions){
        question = questions[i];
        valid_hazards[question.hazard] = layers[question.hazard].title;
    }
    hazard_populate(valid_hazards);
}

function_populate = function(valid_functions){
    function_options = get_options(valid_functions);

    $('#functionlist').html('');
    $('#functionlist').html(function_options);
    $('#functionlist').removeAttr('disabled');
    $('#functionlabel').css('opacity', 1);
    $('#functionlist').change(function_change);
};


exposure_change = function() {
    hazard_name =  $('#hazardlist option:selected').val();
    exposure_name =  $('#exposurelist option:selected').val();

    // Add layer to the map
    add_exposure_layer(exposure_name);

    var valid_functions = {};
    for (i in questions){
        question = questions[i];
        if ((question.hazard == hazard_name) && (question.exposure == exposure_name)){
            valid_functions[question.function] = functions[question.function].title;
        }
    }
    function_populate(valid_functions);
};

exposure_populate = function(valid_exposures) {
    exposure_options = get_options(valid_exposures);
    $('#exposurelist').html('');
    $('#exposurelist').html(exposure_options);
    $('#exposurelist').removeAttr('disabled');
    $('#exposurelabel').css('opacity', 1); 

    $('#exposurelist').change(exposure_change);
};

hazard_change = function() {
    hazard_name =  $('#hazardlist option:selected').val();
    add_hazard_layer(hazard_name);

    // Filter the list of exposures that can be used with this dataset.
    var valid_exposures = {};
    for (i in questions){
        question = questions[i];
        if (question.hazard == hazard_name){
            valid_exposures[question.exposure] = layers[question.exposure].title;
        }
    }
    exposure_populate(valid_exposures);
};

hazard_populate = function(valid_hazards){
    hazard_options = get_options(valid_hazards, 'name', 'title');
    $("#hazardlist").html(hazard_options);
    $('#hazardlist').attr('disabled', false);
    // wire this after initializing, to avoid enabling the exposure one before time
    $('#hazardlist').change(hazard_change);
};

function disable_all(){
    $('#hazardlist').attr('disabled', true);
    $('#exposurelist').attr('disabled', true);
    $('#functionlist').attr('disabled', true);
}

function safe_init(){
    // Save reference to map object.
    map = window.maps.pop();
    window.maps.push(map);

    disable_all();
    $('#exposurelabel').css('opacity', 0.1);
    $('#functionlabel').css('opacity', 0.1);

    $.ajax({
      url: "/safe/api/v1/questions/",  
      success: questions_received,
      error: function(r){  
        alert('Error: ' + r);  
      }  
    });
}

function safemapInit(map, bounds){
    // Add attribution (to replace, Powered by Leaflet)
    map.attributionControl.setPrefix('Powered by MapBox Streets and OSM data');

    map.removeLayer('background');

    var mapbox_streets = L.tileLayer('http://{s}.tiles.mapbox.com/v3/mapbox.mapbox-streets/{z}/{x}/{y}.png')

    var baseMaps = {
        "MapBox Streets": mapbox_streets,
    };

    var overlayMaps = {
    };

    // Add a layer control object, to turn layers off and on
    control = L.control.layers(baseMaps, overlayMaps);
    control.addTo(map);

    // Initialize safe forms
    safe_init();
}