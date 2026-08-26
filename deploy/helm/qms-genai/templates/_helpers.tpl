{{- define "qms-genai.name" -}}
{{ .Chart.Name }}
{{- end -}}

{{- define "qms-genai.labels" -}}
app.kubernetes.io/name: {{ include "qms-genai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: helm
{{- end -}}

{{- define "qms-genai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "qms-genai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "qms-genai.envList" -}}
{{- range $k, $v := .Values.env }}
- name: {{ $k }}
  value: {{ $v | quote }}
{{- end }}
{{- end -}}
