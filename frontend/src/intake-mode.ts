/** Display provenance without promoting fixtures or manual choices into model results. */
export function intakeMode(mode: string | null | undefined): { label: string; description: string } {
  if (mode === 'deterministic') return { label: 'Deterministic rules', description: 'Request interpretation uses rules and makes no model call.' };
  if (mode?.startsWith('deterministic') || mode?.includes('guard')) return { label: 'Deterministic safety check', description: 'A deterministic check sent this request for clarification; no model result authorized a recovery.' };
  if (mode === 'local-model') return { label: 'Local AI · CPU', description: 'Local language model inference interprets the request. It cannot supply order identity, amounts, permissions or warehouse evidence.' };
  if (mode === 'operator-selected') return { label: 'Operator selected', description: 'An operator selected the request type; this is not model interpretation.' };
  if (mode === 'operator-clarified') return { label: 'Operator clarified', description: 'An operator clarified the request; the recovery plan still requires current evidence and approval.' };
  if (mode?.includes('fixture') || mode?.includes('recorded')) return { label: 'Recorded fixture', description: 'This is a recorded test result, not a live model call or real integration verification.' };
  if (mode?.includes('model') || mode?.includes('openai')) return { label: 'Configured model', description: 'A configured model interprets the request. Recovery permissions and amounts remain backend controlled.' };
  return { label: mode ? mode.replaceAll('-', ' ').replaceAll('_', ' ') : 'Mode unavailable', description: 'The result provenance is reported by the service. Review the evidence before taking action.' };
}
