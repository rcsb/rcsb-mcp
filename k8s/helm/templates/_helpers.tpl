{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "helm_chart.fullname" -}}
{{- if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "helm_chart.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "helm_chart.labels" -}}
helm.sh/chart: {{ include "helm_chart.chart" . }}
{{ include "helm_chart.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "helm_chart.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Persistent volume name. Utilize namespace aware naming to allow deployments of cluster resources for different environments.
*/}}
{{- define "helm_chart.pvname" -}}
{{- printf "%s-%s" .Release.Namespace .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
ConfigMap resource name. Ensure names conform to character limits in Kubernetes
*/}}
{{- define "helm_chart.configmapName" -}}
{{- printf "%s-config" (include "helm_chart.fullname" . | trunc 56 | trimSuffix "-") }}
{{- end }}