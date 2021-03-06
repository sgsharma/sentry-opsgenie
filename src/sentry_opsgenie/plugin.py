"""
sentry_opsgenie.plugin
~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2015 by Sentry Team, see AUTHORS for more details.
:license: Apache 2.0, see LICENSE for more details.
"""
from __future__ import absolute_import

import logging
import sentry_opsgenie

from django import forms
from django.utils.html import escape
from requests import HTTPError

from sentry import http
from sentry.plugins.bases import notify
from sentry.utils import json


class OpsGenieOptionsForm(notify.NotificationConfigurationForm):
    api_key = forms.CharField(
        max_length=255,
        help_text='OpsGenie API key used for authenticating API requests',
        required=True,
    )
    recipients = forms.CharField(
        max_length=255,
        help_text='The user names of individual users or groups (comma seperated)',
        required=False,
    )
    alert_url = forms.CharField(
        max_length=255,
        label='OpsGenie Alert URL',
        widget=forms.TextInput(attrs={'class': 'span6', 'placeholder': 'e.g. https://api.opsgenie.com/v2/alerts'}),
        help_text='It must be visible to the Sentry server',
        required=True,
    )


class OpsGeniePlugin(notify.NotificationPlugin):
    author = 'Sentry Team'
    author_url = 'https://github.com/getsentry'
    resource_links = (
        ('Bug Tracker', 'https://github.com/getsentry/sentry-opsgenie/issues'),
        ('Source', 'https://github.com/getsentry/sentry-opsgenie'),
    )

    title = 'OpsGenie'
    slug = 'opsgenie'
    description = 'Create OpsGenie alerts out of notifications.'
    conf_key = 'opsgenie'
    version = sentry_opsgenie.VERSION
    project_conf_form = OpsGenieOptionsForm

    logger = logging.getLogger('sentry.plugins.opsgenie')

    def is_configured(self, project):
        return all((
            self.get_option(k, project)
            for k in ('api_key', 'alert_url')
        ))

    def get_form_initial(self, project=None):
        return {
            'alert_url': 'https://api.opsgenie.com/v2/alerts',
        }

    def build_payload(self, group, event):
        payload = {
            'message': event.message,
            'alias': 'sentry: %d' % group.id,
            'source': 'Sentry',
            'details': {
                'Sentry ID': str(group.id),
                'Sentry Group': getattr(group, 'message_short', group.message).encode('utf-8'),
                'Checksum': group.checksum,
                'Project ID': group.project.slug,
                'Project Name': group.project.name,
                'Logger': group.logger,
                'Level': group.get_level_display(),
                'URL': group.get_absolute_url(),
            },
            'entity': group.culprit,
        }

        payload['tags'] = ['%s:%s' % (str(x).replace(',', ''), str(y).replace(',', '')) for x, y in event.get_tags()]
        
        return payload

    def notify_users(self, group, event, fail_silently=False, **kwargs):
        if not self.is_configured(group.project):
            return

        api_key = self.get_option('api_key', group.project)
        recipients = self.get_option('recipients', group.project)
        alert_url = self.get_option('alert_url', group.project)

        payload = self.build_payload(group, event)

        headers = {'Authorization': 'GenieKey ' + api_key}

        if recipients:
            payload['recipients'] = recipients

        resp = http.safe_urlopen(alert_url, json=payload, headers=headers)
        if not resp.ok:
            raise HTTPError('Unsuccessful response from OpsGenie: %s' % resp.json())
