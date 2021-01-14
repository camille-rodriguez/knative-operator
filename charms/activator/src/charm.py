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


class ServingActivatorCharm(CharmBase):
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
        self.unit.status = MaintenanceStatus("Installing Knative Activator...")
        # try:
            #image_info = self.image.fetch()
        image_info = "gcr.io/knative-releases/knative.dev/serving/cmd/activator@sha256:1e3db4f2eeed42d3ef03f41cc3d07c333edab92af3653a530d6d5f370da96ab6"
        # except OCIImageResourceError:
        #     logging.exception('An error occured while fetching the image info')
        #     self.unit.status = BlockedStatus("Error fetching image information")
        #     return

        self.model.pod.set_spec(
            {
                'version': 3,
                'containers': [{
                    'name': 'activator',
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
                        'containerPort': 8012,
                        'name': 'http1'
                        },
                        {
                        'containerPort': 8013,
                        'name': 'h2c'
                        },
                    ],
                    'envConfig': {
                        'GOGC': '500',
                        'POD_NAME':{
                            'field': {
                                'path': "metadata.name"
                            }
                        },
                        'POD_IP':{
                            'field': {
                                'path': "status.podIP"
                            }
                        },
                        'SYSTEM_NAMESPACE':{
                            'field': {
                                'path': "metadata.namespace"
                            }
                        },
                        'CONFIG_LOGGING_NAME':'config-logging',
                        'CONFIG_OBSERVABILITY_NAME': 'config-observability',
                        'METRICS_DOMAIN':'knative.dev/internal/serving',
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
                        'readinessProbe': {
                            'httpGet': {
                                'port': 8012,
                                'httpHeaders': [{
                                    'name': 'k-kubelet-probe',
                                    'value': 'activator',
                                }],
                            },
                            'failureThreshold': 12
                        },
                        'livenessProbe': {
                            'initialDelaySeconds': 15,
                            'failureThreshold': 12,
                            'httpGet': {
                                'port': 8012,
                                'httpHeaders': [{
                                    'name': 'k-kubelet-probe',
                                    'value': 'activator',
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
                            # Need to create a 2nd service because of bug 
                            # lp:https://bugs.launchpad.net/juju/+bug/1902000
                            'name': 'activator-service',
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
                                        'name': 'http',
                                        'port': 80,
                                        'targetPort': 8012,
                                    },
                                    {
                                        'name': 'http2',
                                        'port': 81,
                                        'targetPort': 8013,
                                    }
                                ],
                                'selector': {'app': 'activator'},
                            }
                        }
                    ],
                }
            }
        )
        self.unit.status = ActiveStatus("Ready")


if __name__ == "__main__":
    main(ServingActivatorCharm)
