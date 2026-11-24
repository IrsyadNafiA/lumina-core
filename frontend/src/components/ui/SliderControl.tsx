import React from 'react';

interface SliderControlProps {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  unit?: string;
  disabled?: boolean;
  accentClass?: string;
  onChange: (nextValue: number) => void;
}

export const SliderControl: React.FC<SliderControlProps> = ({
  id,
  label,
  value,
  min,
  max,
  unit = '%',
  disabled = false,
  accentClass = 'accent-cyan-400',
  onChange,
}) => {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <label htmlFor={id} className="font-medium text-slate-300">
          {label}
        </label>
        <span className="font-mono font-semibold text-slate-200">
          {value}
          {unit}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-800 ${accentClass} disabled:cursor-not-allowed disabled:opacity-40`}
      />
    </div>
  );
};
