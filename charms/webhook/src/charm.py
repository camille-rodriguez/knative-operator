#!/usr/bin/env python3
# Copyright 2020 Camille Rodriguez
# See LICENSE file for licensing details.

import logging
import json
from hashlib import md5
import os
from pathlib import Path
import yaml

# from oci_image import OCIImageResource, OCIImageResourceError

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    WaitingStatus,
)

logger = logging.getLogger(__name__)


class ServingWebhookCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("Waiting for leadership")
            return
        # self.image = OCIImageResource(self, 'knative-activator-image')
        self.framework.observe(self.on.install, self._on_start)
        # self.framework.observe(self.on.config_changed, self._on_config_changed)
        # --- initialize states ---
        # self._stored.set_default(config_hash=self._config_hash())
        self._stored.set_default(started=False)
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])
    
    def _on_start(self, event):
        """Occurs upon install, start, upgrade, and possibly config changed."""
        if self._stored.started:
            return
        self.unit.status = MaintenanceStatus("Installing Knative Webhook...")
        # try:
            #image_info = self.image.fetch()
        image_info = "gcr.io/knative-releases/knative.dev/serving/cmd/webhook@sha256:d27b4495ccc304d5a921d847dd1bce82bd2664ce3e5625b57758ebad03542b5f"
        # except OCIImageResourceError:
        #     logging.exception('An error occured while fetching the image info')
        #     self.unit.status = BlockedStatus("Error fetching image information")
        #     return

        self.model.pod.set_spec(
            {
                'version': 3,
                'containers': [{
                    'name': 'webhook',
                    'image': image_info,
                    # 'imageDetails': image_info,
                    'imagePullPolicy': 'Always',
                    'ports': [{
                        'containerPort': 9090,
                        'name': 'metrics'
                        },
                        {
                        'containerPort': 8008,
                        'name': 'profiling'
                        },
                        {
                        'containerPort': 8443,
                        'name': 'https-webhook'
                        },
                    ],
                    'envConfig': {
                        'POD_NAME':{
                            'field': {
                                'path': "metadata.name"
                            }
                        },
                        'SYSTEM_NAMESPACE':{
                            'field': {
                                'path': "metadata.namespace"
                            }
                        },
                        'CONFIG_LOGGING_NAME':'config-logging',
                        'CONFIG_OBSERVABILITY_NAME': 'config-observability',
                        'METRICS_DOMAIN':'knative.dev/serving',
                        'WEBHOOK_PORT':'8443',
                    },
                    'kubernetes': {
                        'securityContext': {
                            'privileged': False,
                            'readOnlyRootFilesystem': True,
                            'runAsNonRoot': True,
                            'capabilities': {
                                'drop': ['ALL']
                            }
                        },
                        # WIP on the probes : container currently crash when probes are enabled
                        'readinessProbe': {
                            'httpGet': {
                                'port': 8443,
                                'scheme': 'HTTPS',
                                'httpHeaders': [{
                                    'name': 'k-kubelet-probe',
                                    'value': 'webhook',
                                }],
                            },
                            'periodSeconds': 1
                        },
                        'livenessProbe': {
                            'initialDelaySeconds': 20,
                            'failureThreshold': 6,
                            'httpGet': {
                                'port': 8443,
                                'httpHeaders': [{
                                    'name': 'k-kubelet-probe',
                                    'value': 'webhook',
                                }],
                            }
                        }
                    },
                }],
            },
            k8s_resources={
                'kubernetesResources': {
                    'services': [
                        {
                            'name': 'webhook',
                            'spec': {
                                'ports': [
                                    {
                                        'name': 'http-metrics',
                                        'port': 9090,
                                        'targetPort': 9090,
                                    },
                                    {
                                        'name': 'http-profiling',
                                        'port': 8008,
                                        'targetPort': 8008,
                                    },
                                    {
                                        'name': 'https-webhook',
                                        'port': 443,
                                        'targetPort': 8443,
                                    }
                                ],
                                'selector': {'role': 'webhook'},
                            }
                        }
                    ],
                    'mutatingWebhookConfigurations': [
                        {
                            'name': 'knative-mutating-webhook-config',
                            'webhooks': [
                                {
                                    'name': 'webhook.serving.knative.dev',
                                    'clientConfig': {
                                        'service': {
                                            'name': 'webhook',
                                            'namespace': self._stored.namespace,
                                        }
                                    },
                                    'admissionReviewVersions': ["v1", "v1beta1"],
                                    'failurePolicy': 'Fail',
                                    'sideEffects': 'None',
                                    'timeoutSeconds': 10,
                                },
                            ]
                        }
                    ],
                    'ValidatingWebhookConfigurations': [
                        {
                            'name': 'knative-validation-webhook-config',
                            'webhooks': [
                                {
                                    'name': 'validation.webhook.serving.knative.dev',
                                    'clientConfig': {
                                        'service': {
                                            'name': 'webhook',
                                            'namespace': self._stored.namespace,
                                        }
                                    },
                                    'admissionReviewVersions': ["v1", "v1beta1"],
                                    'failurePolicy': 'Fail',
                                    'sideEffects': 'None',
                                    'timeoutSeconds': 10,
                                },
                            ]
                        }
                    ]
                }
            }
        )
        self.unit.status = ActiveStatus("Ready")


if __name__ == "__main__":
    main(ServingWebhookCharm)
