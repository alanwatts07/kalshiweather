export default function ModeToggle({ mode, setMode }) {
  return (
    <div className="inline-flex rounded-lg bg-gray-800 p-1">
      {["paper", "live"].map((m) => (
        <button
          key={m}
          onClick={() => setMode(m)}
          className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
            mode === m
              ? "bg-gray-600 text-white"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          {m === "paper" ? "Paper" : "Live"}
        </button>
      ))}
    </div>
  );
}
