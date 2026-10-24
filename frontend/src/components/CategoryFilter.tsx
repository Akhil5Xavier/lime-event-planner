import { CATEGORIES, type Category } from "../api/types";
import { CATEGORY_COLOR, CATEGORY_LABEL } from "../lib/format";

interface Props {
  value: Category[];
  onChange: (value: Category[]) => void;
}

/** Toggle chips; an empty selection means "all categories". */
export default function CategoryFilter({ value, onChange }: Props) {
  const toggle = (c: Category) => onChange(value.includes(c) ? value.filter((v) => v !== c) : [...value, c]);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {CATEGORIES.map((c) => {
        const active = value.includes(c);
        return (
          <button
            key={c}
            type="button"
            onClick={() => toggle(c)}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition ${
              active ? "border-gray-800 bg-gray-800 text-white" : "border-gray-300 bg-white text-gray-700 hover:border-gray-400"
            }`}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: CATEGORY_COLOR[c] }} />
            {CATEGORY_LABEL[c]}
          </button>
        );
      })}
      {value.length > 0 && (
        <button type="button" className="text-xs text-gray-500 underline" onClick={() => onChange([])}>
          Clear
        </button>
      )}
    </div>
  );
}
