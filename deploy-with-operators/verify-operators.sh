``bash
#!/bin/bash
set -e

echo "========================================="
echo "Operator Verification Script"
echo "========================================="
echo ""

# cert-manager
echo "🔒 cert-manager:"
CERT_PODS=$(kubectl get pods -n cert-manager --no-headers 2>/dev/null | wc -l)
CERT_RUNNING=$(kubectl get pods -n cert-manager --no-headers 2>/dev/null | grep -c Running || echo "0")
echo "  Pods: $CERT_RUNNING/$CERT_PODS Running"
CERT_CRDS=$(kubectl get crd 2>/dev/null | grep -c cert-manager)
echo "  CRDs: $CERT_CRDS/6"
echo ""

# Istio
echo "⛵ Istio:"
ISTIO_PODS=$(kubectl get pods -n istio-system --no-headers 2>/dev/null | wc -l)
ISTIO_RUNNING=$(kubectl get pods -n istio-system --no-headers 2>/dev/null | grep -c Running || echo "0")
echo "  Pods: $ISTIO_RUNNING/$ISTIO_PODS Running"
ISTIO_CRDS=$(kubectl get crd 2>/dev/null | grep -c istio)
echo "  CRDs: $ISTIO_CRDS/14+"
ISTIO_READY=$(kubectl get istio --all-namespaces --no-headers 2>/dev/null | grep -c True || echo "0")
echo "  Istio CR Ready: $ISTIO_READY"
echo ""
# LWS
echo "👥 LWS:"
LWS_PODS=$(kubectl get pods -n lws-system --no-headers 2>/dev/null | wc -l)
if [ "$LWS_PODS" -eq 0 ]; then
    LWS_PODS=$(kubectl get pods -n openshift-lws-operator --no-headers 2>/dev/null | wc -l)
    LWS_RUNNING=$(kubectl get pods -n openshift-lws-operator --no-headers 2>/dev/null | grep -c Running || echo "0")
    LWS_NS="openshift-lws-operator"
else
    LWS_RUNNING=$(kubectl get pods -n lws-system --no-headers 2>/dev/null | grep -c Running || echo "0")
    LWS_NS="lws-system"
fi
echo "  Namespace: $LWS_NS"
echo "  Pods: $LWS_RUNNING/$LWS_PODS Running"
LWS_CRDS=$(kubectl get crd 2>/dev/null | grep -c leaderworkerset)
echo "  CRDs: $LWS_CRDS/1"
echo ""

echo "========================================="
echo "Overall Status:"
echo "========================================="

TOTAL_EXPECTED=9  # Adjust based on your deployment
TOTAL_RUNNING=$((CERT_RUNNING + ISTIO_RUNNING + LWS_RUNNING))

if [ "$TOTAL_RUNNING" -ge "$TOTAL_EXPECTED" ] && [ "$CERT_CRDS" -eq 6 ] && [ "$ISTIO_CRDS" -ge 14 ] && [ "$LWS_CRDS" -eq 1 ]; then
    echo "✅ All operators healthy!"
    exit 0
else
    echo "⚠️  Some operators may have issues. Check details above."
    exit 1
fi

