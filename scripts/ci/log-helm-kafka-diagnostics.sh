#!/usr/bin/env bash
# Logs Helm/Kafka diagnostics for nightly prod CI runs.
# Helps debug Kafka entityOperator rendering and Strimzi acceptance issues.
#
# Usage:
#   ./scripts/ci/log-helm-kafka-diagnostics.sh tools
#   ./scripts/ci/log-helm-kafka-diagnostics.sh pre-install
#   ./scripts/ci/log-helm-kafka-diagnostics.sh post-install

set -euo pipefail

NAMESPACE="${NAMESPACE:-self-service-agent-ci-project-1}"
KAFKA_NAME="${KAFKA_NAME:-self-service-agent-kafka}"
CHART_NAME="${CHART_NAME:-self-service-agent}"
PHASE="${1:-all}"

section() {
  echo ""
  echo "========== $1 =========="
}

warn() {
  echo "WARNING: $*"
}

helm_prod_template_args() {
  VERSION="${VERSION:-$(make -s version 2>/dev/null || echo latest)}"
  echo "Using VERSION=${VERSION} for helm template"
  HELM_TEMPLATE_ARGS=(
    "$CHART_NAME" helm
    -n "$NAMESPACE"
    -f helm/values-production.yaml
    --set "requestManagement.knative.eventing.enabled=true"
    --set "image.tag=${VERSION}"
  )
}

log_tools() {
  section "Git commit"
  git rev-parse HEAD 2>/dev/null || true
  git log -1 --oneline 2>/dev/null || true

  section "Helm client"
  command -v helm || true
  helm version

  section "Kubernetes / OpenShift clients"
  command -v kubectl || true
  kubectl version --client=true 2>/dev/null || true
  command -v oc || true
  oc version --client=true 2>/dev/null || true

  section "Cluster access"
  oc whoami 2>/dev/null || kubectl config current-context 2>/dev/null || true
  kubectl cluster-info 2>/dev/null | head -5 || true
  kubectl get ns "$NAMESPACE" -o wide 2>/dev/null || echo "Namespace ${NAMESPACE} not found yet"

  section "AMQ Streams / Strimzi operator (cluster-wide)"
  kubectl get csv -n openshift-operators 2>/dev/null | grep -Ei 'amq-streams|strimzi' || \
    kubectl get csv -A 2>/dev/null | grep -Ei 'amq-streams|strimzi' || echo "(operator CSV not found)"
  kubectl get deploy -n openshift-operators 2>/dev/null | grep -Ei 'amq-streams|strimzi' || true
}

log_pre_install() {
  section "entityOperator values in chart defaults"
  grep -A 6 'entityOperator:' helm/values.yaml 2>/dev/null | head -8 || true
  if [ -f helm/values-production.yaml ]; then
    echo "(values-production.yaml has no entityOperator overrides)"
    grep 'entityOperator' helm/values-production.yaml 2>/dev/null || true
  fi

  helm_prod_template_args
  make helm-depend >/dev/null 2>&1 || true

  section "Rendered Kafka CR (helm template)"
  helm template "${HELM_TEMPLATE_ARGS[@]}" --show-only templates/kafka-cluster.yaml 2>/dev/null | \
    awk '/^kind: Kafka$/,/^---$/' || warn "Could not render kafka-cluster.yaml"

  section "entityOperator serialization check (rendered manifest)"
  KAFKA_YAML="$(helm template "${HELM_TEMPLATE_ARGS[@]}" --show-only templates/kafka-cluster.yaml 2>/dev/null | awk '/^kind: Kafka$/,/^---$/')"
  if [ -z "$KAFKA_YAML" ]; then
    warn "No Kafka manifest rendered (eventing disabled or template missing?)"
  elif echo "$KAFKA_YAML" | grep -q 'entityOperator: null'; then
    warn "Rendered Kafka CR contains 'entityOperator: null' (often rejected by Strimzi / AMQ Streams)"
  elif echo "$KAFKA_YAML" | awk '/^  entityOperator:$/{getline; if ($0 ~ /^---$/ || $0 ~ /^  [a-z]/ || $0 ~ /^kind:/) {print "empty"} else {print "populated"}}' | grep -q '^empty$'; then
    warn "Rendered Kafka CR contains bare 'entityOperator:' with no child keys"
  elif echo "$KAFKA_YAML" | grep -q '^  entityOperator:'; then
    echo "entityOperator key is present in rendered manifest"
    echo "$KAFKA_YAML" | awk '/^  entityOperator:/,/^  [a-zA-Z]/ {print}'
  else
    echo "entityOperator key is omitted from rendered manifest (expected when no operator resources are set)"
  fi

  section "Full helm template kafka-cluster.yaml (for log capture)"
  helm template "${HELM_TEMPLATE_ARGS[@]}" --show-only templates/kafka-cluster.yaml 2>/dev/null || true
}

log_post_install() {
  section "Helm release metadata"
  helm list -n "$NAMESPACE" 2>/dev/null || true
  helm get metadata "$CHART_NAME" -n "$NAMESPACE" 2>/dev/null || echo "(Helm release ${CHART_NAME} not found in ${NAMESPACE})"
  helm history "$CHART_NAME" -n "$NAMESPACE" --max 3 2>/dev/null || true

  section "Kafka / KafkaNodePool resources"
  kubectl get kafka,kafkanodepool -n "$NAMESPACE" -o wide 2>/dev/null || true

  section "Kafka CR spec.entityOperator (live object)"
  if kubectl get kafka "$KAFKA_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo -n "jsonpath .spec.entityOperator="
    kubectl get kafka "$KAFKA_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.entityOperator}' 2>/dev/null || true
    echo ""
    kubectl get kafka "$KAFKA_NAME" -n "$NAMESPACE" -o yaml 2>/dev/null | awk '/^  entityOperator:/,/^  [a-z]/ {print}' | head -20
  else
    warn "Kafka CR ${KAFKA_NAME} not found in ${NAMESPACE}"
  fi

  section "Kafka CR status conditions"
  kubectl get kafka "$KAFKA_NAME" -n "$NAMESPACE" -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason} message={.message}{"\n"}{end}' 2>/dev/null || true

  section "Kafka CR status (first 50 lines)"
  kubectl get kafka "$KAFKA_NAME" -n "$NAMESPACE" -o yaml 2>/dev/null | awk '/^status:/,0' | head -50 || true

  section "KafkaNodePool status"
  kubectl get kafkanodepool -n "$NAMESPACE" -o yaml 2>/dev/null | awk '/^status:/,/^---$/' | head -40 || true

  section "Recent Kafka events"
  kubectl get events -n "$NAMESPACE" --field-selector "involvedObject.kind=Kafka" --sort-by='.lastTimestamp' 2>/dev/null | tail -20 || true

  section "Recent namespace events (last 30)"
  kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' 2>/dev/null | tail -30 || true

  section "Pods not Running/Succeeded (if install failed partially)"
  kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded 2>/dev/null || true
}

case "$PHASE" in
  tools) log_tools ;;
  pre-install) log_pre_install ;;
  post-install) log_post_install ;;
  all) log_tools; log_pre_install; log_post_install ;;
  *)
    echo "Usage: $0 [tools|pre-install|post-install|all]" >&2
    exit 1
    ;;
esac
