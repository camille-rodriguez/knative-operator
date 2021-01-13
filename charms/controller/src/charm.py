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


class ServingControllerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("Waiting for leadership")
            return
        # self.image = OCIImageResource(self, 'knative-controller-image')
        self.framework.observe(self.on.install, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        # --- initialize states ---
        self._stored.set_default(config_hash=self._config_hash())
        self._stored.set_default(started=False)
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])

    def _config_hash(self):
        data = json.dumps({
            'networking-layer': self.model.config['networking-layer'],
        }, sort_keys=True)
        return md5(data.encode('utf8')).hexdigest()
    
    def _on_start(self, event):
        """Occurs upon install, start, upgrade, and possibly config changed."""
        if self._stored.started:
            return
        self.unit.status = MaintenanceStatus("Installing Knative...")
        # try:
            #image_info = self.image.fetch()
        image_info = "gcr.io/knative-releases/knative.dev/serving/cmd/controller@sha256:b2cd45b8a8a4747efbb24443240ac7836b1afc64207da837417862479d2e84c5"
        # except OCIImageResourceError:
        #     logging.exception('An error occured while fetching the image info')
        #     self.unit.status = BlockedStatus("Error fetching image information")
        #     return

        self.model.pod.set_spec(
            {
                'version': 3,
                'serviceAccount': {
                    'roles': [{
                        # ClusterRole knative-serving-namespaced-admin
                        'name': 'namespaced-admin',
                        'global': True,
                        'rules': [
                            {
                                'apiGroups': ['serving.knative.dev'],
                                'resources': ['*'],
                                'verbs': ['*'],
                            },
                            {
                                'apiGroups': ["networking.internal.knative.dev", "autoscaling.internal.knative.dev", "caching.internal.knative.dev"],
                                'resources': ['*'],
                                'verbs': ["get", "list", "watch"],
                            },
                        ],
                    },
                    {
                    # ClusterRole knative-serving-admin
                        'name': "admin",
                        'global': True,
                        'rules': [{
                                'apiGroups': ['serving.knative.dev'],
                                'resources': ['*'],
                                'verbs': ['list'],
                            },] # Rules are automatically filled in by the controller manager.
                    }
                ],
                },
                'containers': [{
                    'name': 'controller',
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
                    },
                }],
                # 'service': {
                #     'annotations': {
                #         'prometheus.io/port': '7472',
                #         'prometheus.io/scrape': 'true'
                #     }
                # },
                'configMaps': {
                    'config-autoscaler': {
                        'example': open("files/configmaps/cm-autoscaler-example.txt").read()
                    },
                    'config-defaults': {
                        'example': open("files/configmaps/cm-defaults-example.txt").read()
                    },
                    'config-deployment': {
                        'example': open("files/configmaps/cm-deployment-example.txt").read(),
                        'queueSidecarImage': 'gcr.io/knative-releases/knative.dev/serving/cmd/queue@sha256:1a569afd4c34e285f6d647633925e2b684899bc8d01b4894047c90b75ca49357'
                    },
                    'config-domain': {
                        'example': open("files/configmaps/cm-domain-example.txt").read()
                    },
                    'config-features': {
                        'example': open("files/configmaps/cm-features-example.txt").read()
                    },
                    'config-gc': {
                        'example': open("files/configmaps/cm-gc-example.txt").read()
                    },
                    'config-leader-election': {
                        'example': open("files/configmaps/cm-leader-election-example.txt").read()
                    },
                    'config-logging': {
                        'example': open("files/configmaps/cm-logging-example.txt").read()
                    },
                    'config-network': {
                        'example': open("files/configmaps/cm-network-example.txt").read()
                    },
                    'config-observability': {
                        'example': open("files/configmaps/cm-observability-example.txt").read()
                    },
                    'config-tracing': {
                        'example': open("files/configmaps/cm-tracing-example.txt").read()
                    },
                }
            },

            k8s_resources=self.k8s_resources_fixed()
            # Workaround for bug LP:1910820
            # {
            # 'kubernetesResources': {
            #     'customResourceDefinitions': [
            #         {'name': crd['metadata']['name'], 'spec': crd['spec']}
            #         for crd in yaml.safe_load_all(Path("files/serving-crds.yaml").read_text())
            #     ]
            # }
            # }
        )
        self.unit.status = ActiveStatus("Ready")

    def k8s_resources_fixed(self):
        #Workaround for bug LP:1910820
        #Remove extra fields under version
        fields_to_remove = ['additionalPrinterColumns', 'schema', 'subresources'] 
        
        k8s_resources_fixed={
            'kubernetesResources': {
                'customResourceDefinitions': [
                    {'name': crd['metadata']['name'], 'spec': crd['spec']}
                    for crd in yaml.safe_load_all(Path("files/serving-crds.yaml").read_text())
                ]
            }
        }
        for i in range(0,len(k8s_resources_fixed['kubernetesResources']['customResourceDefinitions'])):
            for field in fields_to_remove:
                k8s_resources_fixed['kubernetesResources']['customResourceDefinitions'][i]['spec']['versions'][0].pop(field)


        return k8s_resources_fixed

    def _on_config_changed(self, event):
        net_choices = ['ambassador', 'contour', 'gloo', 'istio', 'kong', 'kourier']
        if self.model.config['networking-layer'].lower() not in net_choices:
            self.unit.status = BlockedStatus('Invalid protocol; '
                                             'only "layer2" currently supported')
            return
        current_config_hash = self._config_hash()
        if current_config_hash != self._stored.config_hash:
            self._stored.started = False
            self._stored.config_hash = current_config_hash
            self._on_start(event)


if __name__ == "__main__":
    main(ServingControllerCharm)
