import { XMarkIcon, ClipboardIcon } from "@heroicons/react/24/outline";

export default function RahDescriptionDrawer({ item, onClose }) {
    if (!item) return null;

    const copyText = () => {
        navigator.clipboard.writeText(item.description || "");
    };

    return (
        <div className="fixed inset-0 bg-black/40 flex justify-end z-50">
            <div className="bg-white w-full max-w-xl h-full p-6 overflow-y-auto shadow-xl">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-lg font-semibold">
                        RAH {item.rah_id.toFixed(2)} — {item.details}
                    </h2>
                    <button
                        className="p-2 rounded hover:bg-gray-100"
                        onClick={onClose}
                    >
                        <XMarkIcon className="h-5 w-5 text-gray-600" />
                    </button>
                </div>

                <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {item.description || (
                        <span className="text-gray-400 italic">
              No description yet. (AI backfill may still be running.)
            </span>
                    )}
                </div>

                <div className="flex justify-end mt-6">
                    <button
                        onClick={copyText}
                        className="flex items-center gap-2 px-4 py-2 rounded bg-indigo-600 text-white hover:bg-indigo-700"
                    >
                        <ClipboardIcon className="h-5 w-5" />
                        Copy
                    </button>
                </div>
            </div>
        </div>
    );
}
