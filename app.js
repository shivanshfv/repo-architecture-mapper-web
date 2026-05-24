'use strict';

const $ = (sel) => document.querySelector(sel);

let lastState = null;

function init() {
  $('#depth').addEventListener('input', e => $('#depth-value').textContent = e.target.value);
  $('#max-files').addEventListener('input', e => $('#max-files-value').textContent = e.target.value);
  $('#analyze').addEventListener('click', analyze);
  $('#url').addEventListener('keydown', e => { if (e.key === 'Enter') analyze(); });
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
}

function setStatus(text, kind) {
  const el = $('#status');
  el.textContent = text;
  el.className = 'status ' + (kind || 'info');
}

async function analyze() {
  const url = $('#url').value.trim();
  if (!url) { setStatus('Please paste a GitHub URL.', 'error'); return; }
  const body = {
    url,
    github_token: $('#github-token').value.trim() || null,
    depth: parseInt($('#depth').value, 10),
    max_source_files: parseInt($('#max-files').value, 10),
  };
  setStatus(`Fetching ${url}…`, 'info');
  $('#analyze').disabled = true;
  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    lastState = data;
    let msg = `Analyzed ${data.owner}/${data.repo} (branch: ${data.branch}) — ${data.fetched_file_count} files fetched`;
    if (data.skipped_source_files) msg += ` — ${data.skipped_source_files} source files skipped (raise the cap)`;
    if (data.truncated) msg += ' — GitHub truncated the tree (large repo)';
    setStatus(msg, 'ok');
    render(data);
  } catch (e) {
    setStatus(`Error: ${e.message}`, 'error');
  } finally {
    $('#analyze').disabled = false;
  }
}

function render(data) {
  renderSummary(data);
  renderGraphs(data);
  renderSetup(data);
  renderManifests(data);
  renderContext(data);
}

function renderSummary(data) {
  const p = $('#tab-summary');
  const languages = data.languages || [];
  const layout = data.layout || [];
  const summary = data.edge_summary || {};
  const manifestCount = (data.manifests || []).length;

  const langList = languages.slice(0, 8).map(([l, n]) => `<li><strong>${escapeHtml(l)}</strong>: ${n} files</li>`).join('');
  const layoutList = layout.map(l => `<li><code>${escapeHtml(l)}</code></li>`).join('');

  let edgesHtml = '';
  for (const [lang, s] of Object.entries(summary)) {
    if (!s.edge_count) continue;
    const top = (s.top_imported || []).slice(0, 5).map(x => `<li><code>${escapeHtml(x.name)}</code> — imported ${x.count}x</li>`).join('');
    edgesHtml += `
      <div class="card">
        <h3>${escapeHtml(lang)} imports</h3>
        <p>${s.node_count} modules, ${s.edge_count} edges</p>
        ${top ? `<p><strong>Most imported:</strong></p><ul>${top}</ul>` : ''}
      </div>`;
  }
  if (!edgesHtml) edgesHtml = '<div class="card"><h3>Internal imports</h3><p class="placeholder">No internal edges detected in parsed languages.</p></div>';

  p.innerHTML = `
    <div class="summary-grid">
      <div class="card">
        <h3>Languages (by file count)</h3>
        ${langList ? `<ul>${langList}</ul>` : '<p class="placeholder">None detected.</p>'}
      </div>
      <div class="card">
        <h3>Top-level layout</h3>
        ${layoutList ? `<ul>${layoutList}</ul>` : '<p class="placeholder">Empty.</p>'}
      </div>
      <div class="card">
        <h3>Manifests</h3>
        <p>${manifestCount} found across the repo.</p>
      </div>
      ${edgesHtml}
    </div>
  `;
}

function renderGraphs(data) {
  const p = $('#tab-graphs');
  p.innerHTML = '';
  const graphs = data.graphs || {};
  if (!Object.keys(graphs).length) {
    p.innerHTML = '<p class="placeholder">No internal module edges detected. The repo may be small, single-file, or in a language this app doesn\'t parse.</p>';
    return;
  }
  for (const [lang, g] of Object.entries(graphs)) {
    const section = document.createElement('section');
    section.innerHTML = `
      <h2>${escapeHtml(lang)} module graph</h2>
      <div class="metrics">
        <span><strong>${g.nodes.length}</strong> nodes</span>
        <span><strong>${g.edges.length}</strong> edges</span>
      </div>
      <div class="graph" id="graph-${lang}"></div>
    `;
    p.appendChild(section);
    drawGraph(`graph-${lang}`, g);
  }
}

function drawGraph(elemId, g) {
  const container = document.getElementById(elemId);
  const inDeg = {}, outDeg = {};
  g.edges.forEach(e => {
    outDeg[e.from] = (outDeg[e.from] || 0) + 1;
    inDeg[e.to] = (inDeg[e.to] || 0) + 1;
  });
  const nodes = new vis.DataSet(g.nodes.map(n => {
    const i = inDeg[n] || 0, o = outDeg[n] || 0;
    return {
      id: n,
      label: n,
      value: Math.max(1, i + o),
      title: `${n}\nimported by: ${i}\nimports: ${o}`,
    };
  }));
  const edges = new vis.DataSet(g.edges.map(e => ({
    from: e.from, to: e.to, value: e.weight, arrows: 'to',
  })));
  new vis.Network(container, { nodes, edges }, {
    physics: {
      barnesHut: { gravitationalConstant: -8000, springLength: 120, centralGravity: 0.3 },
      stabilization: { iterations: 200 },
    },
    edges: { color: { opacity: 0.5 }, smooth: false, arrows: { to: { scaleFactor: 0.6 } } },
    nodes: { shape: 'dot', font: { size: 13 } },
    interaction: { hover: true, tooltipDelay: 100 },
  });
}

function renderSetup(data) {
  const p = $('#tab-setup');
  const md = data.setup_md || '';
  p.innerHTML = (window.marked ? marked.parse(md) : `<pre>${escapeHtml(md)}</pre>`);
  if (md) {
    const btn = document.createElement('button');
    btn.className = 'download-btn';
    btn.textContent = 'Download SETUP.md';
    btn.onclick = () => download(`${data.repo}_SETUP.md`, md);
    p.appendChild(btn);
  }
}

function renderManifests(data) {
  const p = $('#tab-manifests');
  p.innerHTML = '';
  const mans = data.manifests || [];
  if (!mans.length) { p.innerHTML = '<p class="placeholder">No dependency manifests detected.</p>'; return; }
  mans.forEach(m => {
    const div = document.createElement('div');
    div.className = 'manifest';
    let html = `<h3><code>${escapeHtml(m.file)}</code> — ${escapeHtml(m.ecosystem)}</h3>`;
    html += `<p><strong>Dependencies (${m.deps.length})</strong></p>`;
    if (m.deps.length) html += `<pre>${escapeHtml(m.deps.join('\n'))}</pre>`;
    if (m.dev_deps && m.dev_deps.length) {
      html += `<p><strong>Dev dependencies (${m.dev_deps.length})</strong></p>`;
      html += `<pre>${escapeHtml(m.dev_deps.join('\n'))}</pre>`;
    }
    if (m.scripts && Object.keys(m.scripts).length) {
      html += `<p><strong>Scripts</strong></p><ul>`;
      for (const [k, v] of Object.entries(m.scripts)) {
        html += `<li><code>${escapeHtml(k)}</code>: ${escapeHtml(v)}</li>`;
      }
      html += `</ul>`;
    }
    div.innerHTML = html;
    p.appendChild(div);
  });
}

function renderContext(data) {
  $('#tab-context').innerHTML = `<p class="placeholder">The full structured-facts blob assembled from the analysis. Useful if you want to feed it elsewhere.</p><pre>${escapeHtml(data.context || '')}</pre>`;
}

function download(filename, text) {
  const blob = new Blob([text], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

init();
