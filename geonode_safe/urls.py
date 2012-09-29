from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('',
                       url(r'^$',
                           'django.views.generic.simple.direct_to_template',
                           {'template': 'geonode_safe/safe.html'},
                           name='calculator'))

urlpatterns += patterns('geonode_safe.views',
                       url(r'^api/v1/calculate/$', 'calculate', name='safe-calculate'),
                       url(r'^api/v1/questions/$', 'questions', name='safe-questions'),
                       url(r'^api/v1/debug/$', 'debug', name='safe-debug'),
)
