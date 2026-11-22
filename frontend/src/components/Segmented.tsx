type Option<T extends string> = { value: T; label: string; disabled?: boolean; danger?: boolean };

type Props<T extends string> = {
  label: string;
  value: T;
  options: Option<T>[];
  disabled: boolean;
  onChange: (value: T) => void;
};

export function Segmented<T extends string>({
  label,
  value,
  options,
  disabled,
  onChange,
}: Props<T>) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((option) => {
        const checked = option.value === value;
        const classes = ["segitem", checked ? "on" : "", checked && option.danger ? "danger" : ""];
        return (
          <label key={option.value} className={classes.join(" ")}>
            <input
              type="radio"
              name={label}
              value={option.value}
              checked={checked}
              disabled={disabled || option.disabled}
              onChange={() => onChange(option.value)}
            />
            {option.label}
          </label>
        );
      })}
    </div>
  );
}
