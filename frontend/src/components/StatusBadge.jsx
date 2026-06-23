import React from 'react';

export default function StatusBadge({ status }) {
  let colorClass = 'status-pending';
  let label = status;

  if (status === 'extracting' || status === 'validating') {
    colorClass = 'status-processing';
  } else if (status === 'completed') {
    colorClass = 'status-completed';
  } else if (status === 'failed') {
    colorClass = 'status-failed';
  }

  return (
    <span className={`status-badge ${colorClass}`}>
      {label}
    </span>
  );
}
