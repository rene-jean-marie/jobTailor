const segmentButtons = document.querySelectorAll('[data-segment]');
const sourceInput = document.querySelector('[data-source-input]');
const sourceText = document.querySelector('[data-source-text]');
const runButton = document.querySelector('[data-run]');
const progressFill = document.querySelector('[data-progress-fill]');
const progressLabel = document.querySelector('[data-progress-label]');
const progressList = document.querySelectorAll('[data-progress-item]');
const atsSlider = document.querySelector('[data-ats]');
const scoreValue = document.querySelector('[data-score]');
const tabs = document.querySelectorAll('[data-tab]');
const preview = document.querySelector('[data-preview]');
const cvButton = document.querySelector('[data-cv-button]');
const cvInput = document.querySelector('[data-cv-file]');
const cvLabel = document.querySelector('[data-cv-label]');
const includeCover = document.querySelector('[data-include-cover]');
const makePdf = document.querySelector('[data-make-pdf]');
const debugArtifacts = document.querySelector('[data-debug]');
const quietMode = document.querySelector('[data-quiet]');
const dryRun = document.querySelector('[data-dry-run]');
const modelInput = document.querySelector('[data-model]');
const temperatureInput = document.querySelector('[data-temperature]');
const outputList = document.querySelector('[data-output-list]');
const errorBox = document.querySelector('[data-error]');

const previews = {
  cv: `SUMMARY\nData-driven analyst with 6+ years building revenue intelligence and automation.\n\nCORE SKILLS\nPython, SQL, LLM pipelines, ATS optimization, analytics.\n\nIMPACT\n- Reframed accomplishments into ATS-friendly outcomes (+32% recruiter callbacks).\n- Automated tailoring workflow for multi-role applications.`,
  cover: `Dear Hiring Manager,\n\nI'm excited to apply for the Quantitative Analyst role. JobTailor highlights my work in risk modeling, portfolio research, and client-ready storytelling.\n\nHighlights\n- Built factor models in Python + SQL across 120k+ rows.\n- Presented insights for executive decision making.\n\nBest regards,\nRene Jean-Marie`,
  audit: `ATS CHECKLIST\n- 92% keyword alignment\n- Clean section headers (Summary, Skills, Experience)\n- Action verbs tuned to role description\n- Removed ambiguous statements\n- Added quant metrics where possible`
};

let isRunning = false;
let jobSource = 'url';
let progressTimer = null;

const steps = [
  'Parsing job description',
  'Mapping skills to ATS keywords',
  'Rewriting impact bullets',
  'Generating cover letter',
  'Exporting PDF pack'
];

function resetProgress() {
  progressFill.style.width = '0%';
  progressLabel.textContent = 'Ready to tailor';
  progressList.forEach((item) => item.classList.remove('active'));
}

function startProgress() {
  let progress = 0;
  let step = 0;
  const stepSize = 92 / steps.length;

  progressLabel.textContent = steps[0];
  progressList.forEach((item, index) => {
    item.textContent = steps[index];
    item.classList.remove('active');
  });

  progressTimer = setInterval(() => {
    progress = Math.min(92, progress + 6);
    progressFill.style.width = `${progress}%`;
    if (progress >= (step + 1) * stepSize && step < steps.length) {
      progressList[step].classList.add('active');
      progressLabel.textContent = steps[step];
      step += 1;
    }
  }, 350);
}

function finishProgress(label) {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
  progressFill.style.width = '100%';
  progressLabel.textContent = label;
}

function setPreview(key, value) {
  previews[key] = value || previews[key];
  const active = document.querySelector('[data-tab].active');
  if (active && active.dataset.tab === key) {
    preview.textContent = previews[key];
  }
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function clearError() {
  errorBox.textContent = '';
  errorBox.hidden = true;
}

segmentButtons.forEach((button) => {
  button.addEventListener('click', () => {
    segmentButtons.forEach((btn) => btn.classList.remove('active'));
    button.classList.add('active');
    jobSource = button.dataset.segment;
    if (jobSource === 'url') {
      sourceInput.placeholder = 'https://www.linkedin.com/jobs/view/...';
      sourceText.value = '';
      sourceText.disabled = true;
      sourceInput.disabled = false;
    } else {
      sourceInput.placeholder = 'Paste job title here';
      sourceInput.disabled = true;
      sourceText.disabled = false;
    }
  });
});

cvButton.addEventListener('click', () => cvInput.click());
cvInput.addEventListener('change', () => {
  const file = cvInput.files && cvInput.files[0];
  cvLabel.textContent = file ? file.name : 'PDF, Markdown, or text accepted';
});

atsSlider.addEventListener('input', (event) => {
  const value = Number(event.target.value);
  scoreValue.textContent = `${Math.min(98, 62 + value)}%`;
});

runButton.addEventListener('click', async () => {
  if (isRunning) return;
  clearError();

  const file = cvInput.files && cvInput.files[0];
  if (!file) {
    showError('Please choose a CV file before running.');
    return;
  }
  if (jobSource === 'url' && !sourceInput.value.trim()) {
    showError('Please provide a job URL.');
    return;
  }
  if (jobSource === 'text' && !sourceText.value.trim()) {
    showError('Please paste the job description text.');
    return;
  }

  isRunning = true;
  runButton.textContent = 'Tailoring...';
  runButton.disabled = true;
  outputList.innerHTML = '';
  resetProgress();
  startProgress();

  const data = new FormData();
  data.append('cv_file', file);
  data.append('job_source', jobSource);
  data.append('job_url', sourceInput.value.trim());
  data.append('job_text', sourceText.value.trim());
  data.append('include_cover_letter', includeCover.checked ? 'true' : 'false');
  data.append('make_pdf', makePdf.checked ? 'true' : 'false');
  data.append('debug_artifacts', debugArtifacts.checked ? 'true' : 'false');
  data.append('quiet', quietMode.checked ? 'true' : 'false');
  data.append('dry_run', dryRun.checked ? 'true' : 'false');
  data.append('model', modelInput.value.trim());
  data.append('temperature', temperatureInput.value.trim());

  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      body: data
    });
    const payload = await response.json();

    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || 'Failed to run JobTailor.');
    }

    finishProgress('Tailor pack ready');
    if (payload.preview) {
      setPreview('cv', payload.preview.cv || previews.cv);
      setPreview('cover', payload.preview.cover || previews.cover);
      setPreview('audit', payload.preview.audit || previews.audit);
    }

    (payload.created_files || []).forEach((path) => {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = `/${path}`;
      link.textContent = path;
      link.target = '_blank';
      item.appendChild(link);
      outputList.appendChild(item);
    });
  } catch (error) {
    finishProgress('Run failed');
    showError(error.message || 'Unexpected error while running JobTailor.');
  } finally {
    runButton.textContent = 'Tailor Again';
    runButton.disabled = false;
    isRunning = false;
  }
});

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    tabs.forEach((btn) => btn.classList.remove('active'));
    tab.classList.add('active');
    preview.textContent = previews[tab.dataset.tab];
  });
});
