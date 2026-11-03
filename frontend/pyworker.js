// Runs student Python in a Web Worker (Pyodide) so a runaway loop can be terminated; no network or file access beyond the browser sandbox.
let pyodide = null; let out = [];
self.onmessage = async (e) => {
  const { id, code } = e.data;
  try {
    if (!pyodide) {
      importScripts('/vendor/pyodide/pyodide.js');
      pyodide = await self.loadPyodide({ indexURL: '/vendor/pyodide/' });
      pyodide.setStdout({ batched: (s) => out.push(s) }); pyodide.setStderr({ batched: (s) => out.push(s) });
    }
    out = [];
    const result = await pyodide.runPythonAsync(code);
    self.postMessage({ id, ok: true, output: out.join('\n'), result: result === undefined ? '' : String(result) });
  } catch (err) { self.postMessage({ id, ok: false, output: out.join('\n'), error: String(err.message || err).split('\n').slice(-6).join('\n') }); }
};
