const state = window.__WORKBENCH_STATE__;

function renderRows(rows) {
  return rows.map((row) => `
    <tr>
      <td>${row.dimension}</td>
      <td>${row.expected}</td>
      <td>${row.rationale}</td>
    </tr>
  `).join("");
}

async function refreshPreview(grade) {
  const response = await fetch(`/scenarios/${state.scenarioGroup}/preview?grade=${encodeURIComponent(grade)}`);
  if (!response.ok) {
    throw new Error("Failed to load scenario preview.");
  }

  const preview = await response.json();
  state.selectedGrade = preview.scenario_key;

  document.querySelector('input[name="scenario_group"]').value = preview.scenario_group;
  document.getElementById("variant-title").textContent = preview.variant_title;
  document.getElementById("behaviour-description").textContent = preview.candidate_profile.behaviour_description;
  document.getElementById("variant-key").textContent = preview.scenario_key;
  document.getElementById("case-prompt").textContent = preview.case_summary.prompt_content;
  document.getElementById("primary-issues").textContent = preview.primary_issues.length ? preview.primary_issues.join(", ") : "None";
  document.getElementById("scenario-key").textContent = preview.scenario_key;

  const rulesList = document.getElementById("behaviour-rules");
  rulesList.innerHTML = preview.candidate_profile.behavioural_rules
    .map((rule) => `<li>${rule}</li>`)
    .join("");

  document.getElementById("rubric-body").innerHTML = renderRows(preview.expected_scores.rubric);
  document.getElementById("interaction-body").innerHTML = renderRows(preview.expected_scores.case_interaction_quality);

  const url = new URL(window.location.href);
  url.searchParams.set("scenario_group", preview.scenario_group);
  url.searchParams.set("grade", preview.scenario_key);
  window.history.replaceState({}, "", url);
}

function bindScenarioPage() {
  const gradeSelect = document.getElementById("grade-select");
  const runForm = document.getElementById("run-form");

  if (!gradeSelect || !runForm) {
    return;
  }

  gradeSelect.addEventListener("change", async (event) => {
    await refreshPreview(event.target.value);
  });

  runForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = runForm.querySelector("button[type='submit']");
    submitter.disabled = true;
    submitter.textContent = "Running...";

    const payload = {
      scenario_group: state.scenarioGroup,
      grade: gradeSelect.value,
      seed: document.getElementById("seed-input").value,
    };

    try {
      const response = await fetch("/runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error("Run creation failed.");
      }
      const run = await response.json();
      window.location.href = `/runs/${run.run_id}`;
    } finally {
      submitter.disabled = false;
      submitter.textContent = "Run scenario";
    }
  });
}

bindScenarioPage();
