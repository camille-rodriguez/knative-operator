# knative-operator

## Description

This charm deploys Knative on any kubernetes cluster managed by Juju. 

Knative components build on top of Kubernetes, abstracting away the complex details and enabling developers to focus on what matters. Built by codifying the best practices shared by successful real-world implementations, Knative solves the "boring but difficult" parts of deploying and managing cloud native services so you don't have to.

## Usage

Knative is composed of two components: Serving and Eventing. This charm currently supports the deployment of the Eventing components. Eventing is composed of 4 charms : controller, activator, autoscaler and webhook.

The choice of networking layer is a feature in progress. Currently, istio is the only networking layer supported by the charms.
