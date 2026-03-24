/**
 * ChatARPES Frontend - Main App Component
 *
 * TODO:
 * - [ ] Chat message interface
 * - [ ] .pxt file upload (drag & drop)
 * - [ ] Inline plot display with download button
 * - [ ] Material property lookup panel
 * - [ ] Auth integration (pending lab lead decision)
 * - [ ] Session management
 */

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-blue-900 text-white p-4">
        <h1 className="text-2xl font-bold">ChatARPES</h1>
        <p className="text-blue-200 text-sm">
          AI Assistant for ARPES Research
        </p>
      </header>

      <main className="max-w-4xl mx-auto p-4">
        {/* Chat interface placeholder */}
        <div className="bg-white rounded-lg shadow p-6 mt-4">
          <p className="text-gray-500 text-center">
            ChatARPES is under development.
          </p>
          <p className="text-gray-400 text-center text-sm mt-2">
            Upload .pxt files and ask questions about your ARPES data.
          </p>
        </div>

        {/* File upload area placeholder */}
        <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 mt-4 text-center">
          <p className="text-gray-400">
            Drag & drop .pxt files here (coming soon)
          </p>
        </div>
      </main>
    </div>
  );
}
