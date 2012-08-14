from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('',
                       url(r'^$',
                           'django.views.generic.simple.direct_to_template',
                           {'template': 'geonode_safe/calculator.html'},
                           name='calculator'))

urlpatterns += patterns('geonode_safe.views',
                       url(r'^api/calculate/$', 'calculate', name='safe-calculate'),
                       url(r'^api/layers/$', 'layers', name='safe-layers'),
                       url(r'^api/functions/$', 'functions', name='safe-functions'),
                       url(r'^api/debug/$', 'debug', name='safe-debug'),
)
