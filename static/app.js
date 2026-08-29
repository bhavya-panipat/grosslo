const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function initHeroParallax() {
  const floats = document.querySelectorAll('.hero-float');
  const hero = document.getElementById('hero');
  if (!floats.length || !hero || prefersReducedMotion) return;
  hero.addEventListener('mousemove', (e) => {
    const rect = hero.getBoundingClientRect();
    const cx = (e.clientX - rect.left) / rect.width - 0.5;
    const cy = (e.clientY - rect.top) / rect.height - 0.5;
    floats.forEach((el, i) => {
      const depth = 18 + (i % 3) * 10;
      el.style.transform = `translate(${cx * depth}px, ${cy * depth}px)`;
    });
  });
}
initHeroParallax();

function initScrollReveal() {
  const cards = document.querySelectorAll('.card');
  if (!cards.length) return;
  if (typeof IntersectionObserver === 'undefined') {
    cards.forEach(c => c.classList.add('in-view')); // fallback: never leave content invisible
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('in-view');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });
  cards.forEach(c => observer.observe(c));
}
initScrollReveal();

function initCardSpotlight() {
  if (prefersReducedMotion) return;
  document.querySelectorAll('.card').forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${e.clientX - rect.left}px`);
      card.style.setProperty('--my', `${e.clientY - rect.top}px`);
      card.classList.add('spotlit');
    });
    card.addEventListener('mouseleave', () => card.classList.remove('spotlit'));
  });
}
initCardSpotlight();

function countUpInto(el, target, prefix = '₹') {
  if (prefersReducedMotion || target === 0) {
    el.textContent = prefix + target.toLocaleString('en-IN');
    return;
  }
  const duration = 650;
  const start = performance.now();
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const value = Math.round(target * eased);
    el.textContent = prefix + value.toLocaleString('en-IN');
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function initHeroCanvas() {
  const canvas = document.getElementById('hero-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let width, height, checkParticles, ambientParticles;
  let mouse = { x: -9999, y: -9999 };

  const CHECK_PATH = [
    { x: 0.24, y: 0.52 }, { x: 0.42, y: 0.72 }, { x: 0.80, y: 0.26 },
  ];

  function pointsAlongPath(path, count) {
    const segLens = [];
    let total = 0;
    for (let i = 0; i < path.length - 1; i++) {
      const dx = path[i + 1].x - path[i].x, dy = path[i + 1].y - path[i].y;
      const len = Math.sqrt(dx * dx + dy * dy);
      segLens.push(len);
      total += len;
    }
    const pts = [];
    for (let i = 0; i < count; i++) {
      let d = (i / (count - 1)) * total;
      let seg = 0;
      while (seg < segLens.length - 1 && d > segLens[seg]) { d -= segLens[seg]; seg++; }
      const t = segLens[seg] ? d / segLens[seg] : 0;
      const a = path[seg], b = path[seg + 1];
      pts.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
    }
    return pts;
  }

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    width = canvas.width = rect.width;
    height = canvas.height = rect.height;

    const targets = pointsAlongPath(CHECK_PATH, 50);
    checkParticles = targets.map(t => ({
      tx: t.x * width, ty: t.y * height,
      x: Math.random() * width, y: Math.random() * height,
      delay: Math.random() * 500,
      jitterPhase: Math.random() * Math.PI * 2,
      pulseAt: Math.random() * 6000,
    }));

    ambientParticles = [];
    for (let i = 0; i < 55; i++) {
      ambientParticles.push({
        x: Math.random() * width, y: Math.random() * height,
        phase: Math.random() * Math.PI * 2,
        vx: (Math.random() - 0.5) * 0.15, vy: (Math.random() - 0.5) * 0.15,
      });
    }
  }
  resize();
  window.addEventListener('resize', resize);

  if (!prefersReducedMotion) {
    canvas.parentElement.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
    });
    canvas.parentElement.addEventListener('mouseleave', () => { mouse.x = -9999; mouse.y = -9999; });
  }

  if (prefersReducedMotion) {
    ctx.fillStyle = 'rgba(141,151,172,0.16)';
    ambientParticles.forEach(p => { ctx.beginPath(); ctx.arc(p.x, p.y, 1.2, 0, Math.PI * 2); ctx.fill(); });
    ctx.fillStyle = 'rgba(78,240,192,0.9)';
    checkParticles.forEach(p => { ctx.beginPath(); ctx.arc(p.tx, p.ty, 2, 0, Math.PI * 2); ctx.fill(); });
    return;
  }

  const start = performance.now();
  const NETWORK_DIST = 90;

  function draw(t) {
    ctx.clearRect(0, 0, width, height);

    // Ambient particles drift slowly and gently avoid the cursor.
    ambientParticles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;
      const dx = p.x - mouse.x, dy = p.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      let x = p.x, y = p.y;
      if (dist < 70) {
        const push = (70 - dist) / 70;
        x += (dx / (dist || 1)) * push * 14;
        y += (dy / (dist || 1)) * push * 14;
      }
      p.renderX = x; p.renderY = y;
    });

    // Network lines between nearby ambient particles.
    ctx.lineWidth = 0.6;
    for (let i = 0; i < ambientParticles.length; i++) {
      for (let j = i + 1; j < ambientParticles.length; j++) {
        const a = ambientParticles[i], b = ambientParticles[j];
        const dx = a.renderX - b.renderX, dy = a.renderY - b.renderY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < NETWORK_DIST) {
          ctx.strokeStyle = `rgba(78,240,192,${0.12 * (1 - dist / NETWORK_DIST)})`;
          ctx.beginPath();
          ctx.moveTo(a.renderX, a.renderY);
          ctx.lineTo(b.renderX, b.renderY);
          ctx.stroke();
        }
      }
    }

    ambientParticles.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.renderX, p.renderY, 1.3, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(141,151,172,0.35)';
      ctx.fill();
    });

    checkParticles.forEach(p => {
      const elapsed = t - start - p.delay;
      const progress = Math.min(Math.max(elapsed / 1400, 0), 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const settled = progress >= 1;
      const jitterX = settled ? Math.sin(t / 2200 + p.jitterPhase) * 1.3 : 0;
      const jitterY = settled ? Math.cos(t / 2600 + p.jitterPhase) * 1.3 : 0;
      const x = p.x + (p.tx - p.x) * eased + jitterX;
      const y = p.y + (p.ty - p.y) * eased + jitterY;
      const pulse = settled && ((t + p.pulseAt) % 6000) < 400;
      ctx.beginPath();
      ctx.arc(x, y, pulse ? 3.4 : 2.2, 0, Math.PI * 2);
      ctx.fillStyle = pulse ? 'rgba(167,139,250,0.95)' : 'rgba(78,240,192,0.9)';
      ctx.shadowColor = 'rgba(78,240,192,0.8)';
      ctx.shadowBlur = pulse ? 10 : 5;
      ctx.fill();
      ctx.shadowBlur = 0;
    });

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
}
initHeroCanvas();

async function checkAiStatus() {
  const el = document.getElementById('ai-status');
  try {
    const res = await fetch('/health');
    const data = await res.json();
    if (data.ai_layer_active) {
      el.textContent = 'AI layer active (Claude API connected)';
      el.className = 'ai-status active';
    } else {
      el.textContent = 'AI layer unavailable — no API key configured, using rule-based fallback';
      el.className = 'ai-status fallback';
    }
  } catch (e) {
    el.textContent = 'Could not reach server';
  }
}
checkAiStatus();

let lastExtractedStructure = null;
let lastExtractionAiBacked = false;

document.getElementById('extract-btn').addEventListener('click', async () => {
  const text = document.getElementById('offer-text').value;
  const resultEl = document.getElementById('extract-result');
  if (!text.trim()) {
    resultEl.textContent = 'Paste some offer letter text first.';
    resultEl.className = 'result-block warning';
    resultEl.classList.remove('hidden');
    return;
  }
  resultEl.textContent = 'Extracting…';
  resultEl.className = 'result-block';
  resultEl.classList.remove('hidden');

  const res = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  const data = await res.json();

  if (data.ctc) document.getElementById('ctc-input').value = data.ctc;

  // Remember the as-extracted structure (basic is the field that matters
  // most — negotiation has nothing to compare against without it) so the
  // Optimize step can send it along for the negotiation copilot.
  lastExtractedStructure = data.basic ? {
    basic: data.basic, hra: data.hra, lta: data.lta, employer_pf: data.employer_pf,
  } : null;
  lastExtractionAiBacked = data.ai_backed || false;

  let html = `<strong>Extracted</strong> <span class="source-tag ${data.ai_backed ? 'ai' : ''}">${data.ai_backed ? 'AI-extracted' : 'rule-based fallback'}</span><br>`;
  html += `CTC: ${data.ctc ?? 'not found'} | Basic: ${data.basic ?? '—'} | HRA: ${data.hra ?? '—'} | LTA: ${data.lta ?? '—'} | Special allowance: ${data.special_allowance ?? '—'}`;
  if (data.mismatch_warning) {
    html += `<br><strong>⚠ ${data.mismatch_warning}</strong>`;
    resultEl.className = 'result-block warning';
  }
  if (!data.basic) {
    html += `<br><em>No basic salary found — negotiation comparison won't be available; tax optimization will still run.</em>`;
  }
  html += `<br><em>Please verify the CTC field above before optimizing — extraction is not guaranteed accurate.</em>`;
  resultEl.innerHTML = html;
});

document.getElementById('optimize-btn').addEventListener('click', async () => {
  const ctc = document.getElementById('ctc-input').value;
  const rent = document.getElementById('rent-input').value || 0;
  const city = document.getElementById('city-input').value;
  const npsOpted = document.getElementById('nps-input').checked;

  if (!ctc || Number(ctc) <= 0) {
    alert('Enter a valid CTC first.');
    return;
  }

  const btn = document.getElementById('optimize-btn');
  btn.disabled = true;
  btn.textContent = 'Optimizing…';

  try {
    const body = { ctc: Number(ctc), rent_paid: Number(rent), city, nps_opted: npsOpted };
    if (lastExtractedStructure) body.current_structure = lastExtractedStructure;
    const res = await fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) {
      alert(data.error);
      return;
    }
    renderResults(data);

    // Sensitivity sweep — separate lightweight call, doesn't block the main result.
    try {
      const sensRes = await fetch('/api/sensitivity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rent_paid: Number(rent), city, nps_opted: npsOpted }),
      });
      const sensData = await sensRes.json();
      const sensEl = document.getElementById('sensitivity-chart-wrap');
      sensEl.innerHTML = `<h3>Regime crossover across CTC (rent held at ₹${Number(rent).toLocaleString('en-IN')})</h3>${buildSensitivityChart(sensData.points)}`;
      animateSensitivity(sensEl);
    } catch (e) {
      // Non-critical — main result already rendered successfully.
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Optimize';
  }
});

function buildComparisonChart(oldTax, newTax, recommendedRegime) {
  const max = Math.max(oldTax, newTax) * 1.1 || 1;
  const barW = 90, gap = 60, chartW = 320, chartH = 160, baseY = 140;
  const oldH = (oldTax / max) * 110;
  const newH = (newTax / max) * 110;
  const oldClass = recommendedRegime === 'old' ? 'bar-recommended' : 'bar-other';
  const newClass = recommendedRegime === 'new' ? 'bar-recommended' : 'bar-other';
  return `
    <svg viewBox="0 0 ${chartW} ${chartH}" class="chart" role="img" aria-label="Old regime tax versus new regime tax, recommended regime highlighted">
      <line x1="20" y1="${baseY}" x2="${chartW - 10}" y2="${baseY}" stroke="var(--rule)" stroke-width="1"/>
      <rect class="bar ${oldClass}" x="60" y="${baseY}" width="${barW}" height="0" data-h="${oldH}" rx="3"/>
      <text x="${60 + barW / 2}" y="${baseY + 18}" text-anchor="middle" class="chart-label">Old${recommendedRegime === 'old' ? ' ✓' : ''}</text>
      <text x="${60 + barW / 2}" y="${baseY - oldH - 8}" text-anchor="middle" class="chart-value mono">₹${Math.round(oldTax).toLocaleString('en-IN')}</text>
      <rect class="bar ${newClass}" x="${60 + barW + gap}" y="${baseY}" width="${barW}" height="0" data-h="${newH}" rx="3"/>
      <text x="${60 + barW + gap + barW / 2}" y="${baseY + 18}" text-anchor="middle" class="chart-label">New${recommendedRegime === 'new' ? ' ✓' : ''}</text>
      <text x="${60 + barW + gap + barW / 2}" y="${baseY - newH - 8}" text-anchor="middle" class="chart-value mono">₹${Math.round(newTax).toLocaleString('en-IN')}</text>
    </svg>`;
}

function animateBars(svgEl) {
  const bars = svgEl.querySelectorAll('.bar');
  if (prefersReducedMotion) {
    bars.forEach(b => { b.setAttribute('height', b.dataset.h); b.setAttribute('y', 140 - b.dataset.h); });
    return;
  }
  bars.forEach((b, i) => {
    const target = parseFloat(b.dataset.h);
    const start = performance.now() + i * 100;
    function tick(now) {
      const progress = Math.min(Math.max((now - start) / 500, 0), 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const h = target * eased;
      b.setAttribute('height', h);
      b.setAttribute('y', 140 - h);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
}

const COMPOSITION_COLORS = {
  basic: '#4EF0C0', hra: '#A78BFA', lta: '#FFB86B',
  special_allowance: '#6EA8FE', employer_pf: '#7C88A0', employer_nps: '#F472B6',
};
const COMPOSITION_LABELS = {
  basic: 'Basic', hra: 'HRA', lta: 'LTA', special_allowance: 'Special allowance',
  employer_pf: 'Employer PF', employer_nps: 'Employer NPS',
};

function buildIsoStack(structure) {
  const keys = ['basic', 'hra', 'lta', 'special_allowance', 'employer_pf', 'employer_nps'];
  const total = keys.reduce((sum, k) => sum + (structure[k] || 0), 0) || 1;
  const stackHeight = 190;
  let cumulative = 0;
  const blocks = keys.map((k, i) => {
    const val = structure[k] || 0;
    const h = (val / total) * stackHeight;
    const bottom = cumulative;
    cumulative += h;
    return { key: k, val, h, bottom, delay: i * 90 };
  });

  const blockDivs = blocks.filter(b => b.val > 0).map(b =>
    `<div class="iso-block" data-delay="${b.delay}" style="height:${b.h.toFixed(1)}px; bottom:${b.bottom.toFixed(1)}px; background:${COMPOSITION_COLORS[b.key]}; box-shadow:0 0 18px ${COMPOSITION_COLORS[b.key]}55;"></div>`
  ).join('');

  const legend = blocks.filter(b => b.val > 0).map(b =>
    `<div class="iso-legend-item"><span class="iso-swatch" style="background:${COMPOSITION_COLORS[b.key]}"></span>${COMPOSITION_LABELS[b.key]} <span class="mono">${Math.round(b.val / total * 100)}%</span></div>`
  ).join('');

  return `<div class="iso-stack-wrap">
    <div class="iso-stack" role="img" aria-label="Where the recommended CTC goes, as a stacked breakdown">
      <div class="iso-stack-inner">${blockDivs}</div>
    </div>
    <div class="iso-legend">${legend}</div>
  </div>`;
}

function animateIsoStack(wrapEl) {
  const blocks = wrapEl.querySelectorAll('.iso-block');
  if (prefersReducedMotion) {
    blocks.forEach(b => b.classList.add('settled'));
    return;
  }
  blocks.forEach(b => {
    const delay = parseFloat(b.dataset.delay) || 0;
    setTimeout(() => b.classList.add('settled'), delay);
  });
}

function buildSensitivityChart(points) {
  const chartW = 340, chartH = 180, padL = 44, padB = 24, padT = 12, padR = 10;
  const plotW = chartW - padL - padR, plotH = chartH - padT - padB;
  const maxTax = Math.max(...points.map(p => Math.max(p.old_tax, p.new_tax))) * 1.08 || 1;
  const minCtc = points[0].ctc, maxCtc = points[points.length - 1].ctc;

  const xFor = ctc => padL + ((ctc - minCtc) / (maxCtc - minCtc)) * plotW;
  const yFor = tax => padT + plotH - (tax / maxTax) * plotH;

  const oldPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xFor(p.ctc).toFixed(1)} ${yFor(p.old_tax).toFixed(1)}`).join(' ');
  const newPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xFor(p.ctc).toFixed(1)} ${yFor(p.new_tax).toFixed(1)}`).join(' ');

  let crossoverX = null;
  for (let i = 1; i < points.length; i++) {
    if (points[i].recommended_regime !== points[i - 1].recommended_regime) {
      crossoverX = xFor((points[i].ctc + points[i - 1].ctc) / 2);
      break;
    }
  }

  const fmtCtc = ctc => ctc >= 100000 ? `₹${(ctc / 100000).toFixed(0)}L` : `₹${ctc}`;
  const xTicks = [0, Math.floor(points.length / 2), points.length - 1].map(i =>
    `<text x="${xFor(points[i].ctc)}" y="${chartH - 6}" text-anchor="middle" class="chart-label">${fmtCtc(points[i].ctc)}</text>`
  ).join('');

  return `
    <svg viewBox="0 0 ${chartW} ${chartH}" class="chart sensitivity" role="img" aria-label="Tax under old versus new regime across a range of CTC values, rent held constant">
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${chartH - padB}" stroke="var(--rule)" stroke-width="1"/>
      <line x1="${padL}" y1="${chartH - padB}" x2="${chartW - padR}" y2="${chartH - padB}" stroke="var(--rule)" stroke-width="1"/>
      ${crossoverX !== null ? `<line x1="${crossoverX}" y1="${padT}" x2="${crossoverX}" y2="${chartH - padB}" stroke="var(--brass)" stroke-width="1" stroke-dasharray="3,3"/>` : ''}
      <path d="${oldPath}" fill="none" stroke="#C9C3B4" stroke-width="2" class="sens-line" pathLength="1"/>
      <path d="${newPath}" fill="none" stroke="var(--forest)" stroke-width="2" class="sens-line" pathLength="1"/>
      ${xTicks}
    </svg>
    <div class="chart-legend">
      <span class="legend-item"><span class="swatch" style="background:#C9C3B4"></span>Old regime</span>
      <span class="legend-item"><span class="swatch" style="background:var(--forest)"></span>New regime</span>
      ${crossoverX !== null ? '<span class="legend-item mono">┈ crossover point</span>' : '<span class="legend-item">No crossover in this range — one regime wins throughout</span>'}
    </div>`;
}

function animateSensitivity(wrapEl) {
  const lines = wrapEl.querySelectorAll('.sens-line');
  if (prefersReducedMotion) return;
  lines.forEach(line => {
    line.style.strokeDasharray = '1';
    line.style.strokeDashoffset = '1';
    line.getBoundingClientRect();
    line.style.transition = 'stroke-dashoffset 0.9s ease';
    requestAnimationFrame(() => { line.style.strokeDashoffset = '0'; });
  });
}

function buildCapabilityStrip(data) {
  const items = [];

  items.push({
    name: 'Extraction',
    ran: lastExtractedStructure !== null,
    aiBacked: lastExtractionAiBacked,
    note: lastExtractedStructure !== null ? null : 'not run this pass',
  });

  items.push({
    name: 'Explanation',
    ran: true,
    aiBacked: data.explanation.ai_backed,
    note: data.explanation.guard_triggered ? 'guard rejected AI output' : null,
  });

  items.push({
    name: 'Compliance',
    ran: true,
    aiBacked: data.compliance.ai_backed,
    note: `${data.compliance.flags.length} flag${data.compliance.flags.length === 1 ? '' : 's'}`,
  });

  items.push({
    name: 'Negotiation',
    ran: !!data.negotiation,
    aiBacked: data.negotiation ? data.negotiation.ai_backed : false,
    note: !data.negotiation
      ? 'needs an extracted offer letter'
      : (data.negotiation.total_annual_saving > 0 ? null : 'already optimal'),
  });

  return items.map(item => {
    let statusClass = 'not-run';
    let statusText = 'not run';
    if (item.ran) {
      statusClass = item.aiBacked ? 'ai' : 'fallback';
      statusText = item.aiBacked ? 'AI-backed' : 'rule-based';
    }
    return `<div class="cap-item ${statusClass}">
      <span class="cap-name">${item.name}</span>
      <span class="cap-status">${statusText}</span>
      ${item.note ? `<span class="cap-note">${item.note}</span>` : ''}
    </div>`;
  }).join('');
}

function renderResults(data) {
  document.getElementById('results').classList.remove('hidden');
  document.getElementById('capability-strip').innerHTML = buildCapabilityStrip(data);

  const recTax = data.recommended_regime === 'old'
    ? data.old_regime_best.tax_breakdown.total_tax
    : data.new_regime_best.tax_breakdown.total_tax;

  document.getElementById('recommendation').innerHTML =
    `Recommended: ${data.recommended_regime === 'old' ? 'Old' : 'New'} regime — saves <span id="saving-figure" class="mono"></span>/year vs the other regime (tax: <span class="mono">₹${recTax.toLocaleString('en-IN')}</span>)`;
  countUpInto(document.getElementById('saving-figure'), Math.round(data.annual_saving));

  const recStructure = data.recommended_regime === 'old' ? data.old_regime_best.structure : data.new_regime_best.structure;
  const compChartEl = document.getElementById('composition-chart-wrap');
  compChartEl.innerHTML = `<h3>Where the recommended ₹${data.ctc.toLocaleString('en-IN')} CTC goes</h3>${buildIsoStack(recStructure)}`;
  animateIsoStack(compChartEl);

  const regimeChartEl = document.getElementById('regime-chart-wrap');
  regimeChartEl.innerHTML = `<h3>Old regime vs new regime — total tax</h3>${buildComparisonChart(data.old_regime_best.tax_breakdown.total_tax, data.new_regime_best.tax_breakdown.total_tax, data.recommended_regime)}`;
  animateBars(regimeChartEl.querySelector('svg'));

  const exp = data.explanation;
  document.getElementById('explanation').innerHTML =
    `${exp.explanation} <span class="source-tag ${exp.ai_backed ? 'ai' : ''}">${exp.ai_backed ? 'AI-generated' : 'rule-based'}</span>` +
    (exp.guard_triggered ? ' <span class="source-tag">note: AI output failed numeric verification, showing fallback</span>' : '');

  const compEl = document.getElementById('compliance');
  compEl.innerHTML = '';
  if (data.compliance.flags.length === 0) {
    compEl.innerHTML = '<div class="flag Low">No compliance flags for this structure.</div>';
  } else {
    data.compliance.flags.forEach(f => {
      const div = document.createElement('div');
      div.className = `flag ${f.severity}`;
      div.textContent = `[${f.rule_id}] ${f.message}`;
      compEl.appendChild(div);
    });
  }

  const negEl = document.getElementById('negotiation');
  if (data.negotiation) {
    const neg = data.negotiation;
    negEl.classList.remove('hidden');
    let html = `<h3>Negotiation talking points</h3>`;
    if (neg.total_annual_saving > 0) {
      html += `<p>${neg.points} <span class="source-tag ${neg.ai_backed ? 'ai' : ''}">${neg.ai_backed ? 'AI-generated' : 'rule-based'}</span>` +
        (neg.guard_triggered ? ` <span class="source-tag">note: AI output failed numeric verification, showing fallback</span>` : '') +
        `</p>`;
    } else {
      html += `<p>${neg.points}</p>`;
    }
    negEl.innerHTML = html;
  } else {
    negEl.classList.add('hidden');
    negEl.innerHTML = '';
  }

  const table = document.getElementById('comparison-table');
  const old = data.old_regime_best;
  const nw = data.new_regime_best;
  table.innerHTML = `
    <tr><th></th><th>Old regime</th><th>New regime</th></tr>
    <tr><td>Basic</td><td>₹${old.structure.basic.toLocaleString('en-IN')}</td><td>₹${nw.structure.basic.toLocaleString('en-IN')}</td></tr>
    <tr><td>HRA</td><td>₹${old.structure.hra.toLocaleString('en-IN')}</td><td>₹${nw.structure.hra.toLocaleString('en-IN')}</td></tr>
    <tr><td>LTA</td><td>₹${old.structure.lta.toLocaleString('en-IN')}</td><td>₹${nw.structure.lta.toLocaleString('en-IN')}</td></tr>
    <tr><td>Special allowance</td><td>₹${old.structure.special_allowance.toLocaleString('en-IN')}</td><td>₹${nw.structure.special_allowance.toLocaleString('en-IN')}</td></tr>
    <tr><td>Employer PF</td><td>₹${old.structure.employer_pf.toLocaleString('en-IN')}</td><td>₹${nw.structure.employer_pf.toLocaleString('en-IN')}</td></tr>
    <tr><td>Employer NPS</td><td>₹${old.structure.employer_nps.toLocaleString('en-IN')}</td><td>₹${nw.structure.employer_nps.toLocaleString('en-IN')}</td></tr>
    <tr><td><strong>Total tax</strong></td><td><strong>₹${old.tax_breakdown.total_tax.toLocaleString('en-IN')}</strong></td><td><strong>₹${nw.tax_breakdown.total_tax.toLocaleString('en-IN')}</strong></td></tr>
  `;
}
