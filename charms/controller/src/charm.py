#!/usr/bin/env python3
# Copyright 2020 Camille Rodriguez
# See LICENSE file for licensing details.

import logging
import json
from hashlib import md5
import yaml

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


class KnativeOperatorCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("Waiting for leadership")
            return
        self.framework.observe(self.on.install, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        # --- initialize states ---
        self._stored.set_default(config_hash=self._config_hash())
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])

    def _config_hash(self):
        data = json.dumps({
            'iprange': self.model.config['iprange'],
        }, sort_keys=True)
        return md5(data.encode('utf8')).hexdigest()
    
    def _on_start(self, event):
        """Occurs upon install, start, upgrade, and possibly config changed."""
        if self._stored.started:
            return
        self.unit.status = MaintenanceStatus("Installing Knative...")

        self.model.pod.set_spec(
            {
                'version': 3,
                'serviceAccount': {
                    # 'roles': [{
                    #     'global': True,
                    #     'rules': [
                    #         {
                    #             'apiGroups': [''],
                    #             'resources': ['services'],
                    #             'verbs': ['get', 'list', 'watch', 'update'],
                    #         },
                    #         {
                    #             'apiGroups': [''],
                    #             'resources': ['services/status'],
                    #             'verbs': ['update'],
                    #         },
                    #         {
                    #             'apiGroups': [''],
                    #             'resources': ['events'],
                    #             'verbs': ['create', 'patch'],
                    #         },
                    #         {
                    #             'apiGroups': ['policy'],
                    #             'resourceNames': ['controller'],
                    #             'resources': ['podsecuritypolicies'],
                    #             'verbs': ['use'],
                    #         },
                    #     ],
                    # }],
                },
                'containers': [{
                    'name': 'controller',
                    'imageDetails': image_info,
                    'imagePullPolicy': 'Always',
                    'ports': [{
                        'containerPort': 7472,
                        'protocol': 'TCP',
                        'name': 'monitoring'
                    }],
                    # TODO: add constraint fields once it exists in pod_spec
                    # bug : https://bugs.launchpad.net/juju/+bug/1893123
                    # 'resources': {
                    #     'limits': {
                    #         'cpu': '100m',
                    #         'memory': '100Mi',
                    #     }
                    # },
                    'kubernetes': {
                        'securityContext': {
                            'privileged': False,
                            'runAsNonRoot': True,
                            'runAsUser': 65534,
                            'readOnlyRootFilesystem': True,
                            'capabilities': {
                                'drop': ['ALL']
                            }
                        },
                        # fields do not exist in pod_spec
                        # 'TerminationGracePeriodSeconds': 0,
                    },
                }],
                'service': {
                    'annotations': {
                        'prometheus.io/port': '7472',
                        'prometheus.io/scrape': 'true'
                    }
                },
                'configMaps': {
                    'config': {
                        'config': cm
                    }
                }
            },
            k8s_resources={
            'kubernetesResources': {
                'customResourceDefinitions': [
                    {'name': crd['metadata']['name'], 'spec': crd['spec']}
                    for crd in yaml.safe_load_all(Path("files/serving-crds.yaml").read_text())
                ],
            }
            }
        )

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
    main(KnativeOperatorCharm)
