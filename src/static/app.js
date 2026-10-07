document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const messageDiv = document.getElementById("message");
  const accountForms = document.getElementById("account-forms");
  const accountProfile = document.getElementById("account-profile");
  const accountMessage = document.getElementById("account-message");
  const profileSummary = document.getElementById("profile-summary");
  const profileMemberships = document.getElementById("profile-memberships");

  function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, (character) => {
      const replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return replacements[character];
    });
  }

  function showMessage(element, message, kind) {
    element.textContent = message;
    element.className = `message ${kind}`;
    window.setTimeout(() => element.classList.add("hidden"), 5000);
  }

  async function responseData(response) {
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "An error occurred");
    }
    return result;
  }

  async function fetchActivities() {
    try {
      const response = await fetch("/activities");
      const activities = await responseData(response);

      activitiesList.innerHTML = "";
      activitySelect.replaceChildren(activitySelect.options[0]);

      Object.entries(activities).forEach(([name, details]) => {
        const activityCard = document.createElement("div");
        activityCard.className = "activity-card";

        const spotsLeft =
          details.max_participants - details.participants.length;

        const participantsHTML =
          details.participants.length > 0
            ? `<div class="participants-section">
              <h5>Participants:</h5>
              <ul class="participants-list">
                ${details.participants
                  .map(
                    (email) =>
                      `<li><span class="participant-email">${escapeHTML(email)}</span><button class="delete-btn" data-activity="${escapeHTML(name)}" data-email="${escapeHTML(email)}" aria-label="Unregister ${escapeHTML(email)} from ${escapeHTML(name)}">❌</button></li>`
                  )
                  .join("")}
              </ul>
            </div>`
            : "<p><em>No participants yet</em></p>";

        activityCard.innerHTML = `
          <h4>${escapeHTML(name)}</h4>
          <p>${escapeHTML(details.description)}</p>
          <p><strong>Schedule:</strong> ${escapeHTML(details.schedule)}</p>
          <p><strong>Availability:</strong> ${spotsLeft} spots left</p>
          <div class="participants-container">${participantsHTML}</div>
        `;
        activitiesList.appendChild(activityCard);

        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        activitySelect.appendChild(option);
      });

      document.querySelectorAll(".delete-btn").forEach((button) => {
        button.addEventListener("click", handleUnregister);
      });
    } catch (error) {
      activitiesList.textContent =
        "Failed to load activities. Please try again later.";
      console.error("Error fetching activities:", error);
    }
  }

  async function handleUnregister(event) {
    const button = event.currentTarget;
    const activity = button.getAttribute("data-activity");
    const email = button.getAttribute("data-email");

    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(activity)}/unregister?email=${encodeURIComponent(email)}`,
        { method: "DELETE" }
      );
      const result = await responseData(response);
      showMessage(messageDiv, result.message, "success");
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, "error");
      console.error("Error unregistering:", error);
    }
  }

  function renderProfile(profile) {
    accountForms.classList.add("hidden");
    accountProfile.classList.remove("hidden");
    profileSummary.textContent =
      profile.role === "student"
        ? `${profile.name} · ${profile.email} · Grade ${profile.grade_level}`
        : `${profile.name} · ${profile.email} · Advisor`;

    const heading = document.createElement("h4");
    const items =
      profile.role === "student" ? profile.activities : profile.clubs;
    heading.textContent =
      profile.role === "student" ? "My activities" : "My club assignments";
    profileMemberships.replaceChildren(heading);

    if (items.length === 0) {
      const emptyMessage = document.createElement("p");
      emptyMessage.textContent =
        profile.role === "student"
          ? "You are not signed up for any activities yet."
          : "No club assignments yet.";
      profileMemberships.appendChild(emptyMessage);
    } else {
      const list = document.createElement("ul");
      items.forEach((item) => {
        const listItem = document.createElement("li");
        listItem.textContent =
          profile.role === "student"
            ? `${item.name} — ${item.schedule}`
            : `${item.name} — ${item.position} — ${item.schedule}`;
        list.appendChild(listItem);
      });
      profileMemberships.appendChild(list);
    }

    const studentEmail = document.getElementById("email");
    if (profile.role === "student") {
      studentEmail.value = profile.email;
    }
  }

  async function loadProfile() {
    try {
      const response = await fetch("/account");
      if (response.status === 401) {
        accountForms.classList.remove("hidden");
        accountProfile.classList.add("hidden");
        return;
      }
      renderProfile(await responseData(response));
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      console.error("Error loading account:", error);
    }
  }

  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: document.getElementById("account-role").value,
          email: document.getElementById("account-email").value,
          password: document.getElementById("account-password").value,
        }),
      });
      const profile = await responseData(response);
      form.reset();
      renderProfile(profile);
      showMessage(accountMessage, "Signed in successfully", "success");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
    }
  });

  document
    .getElementById("registration-form")
    .addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        const response = await fetch("/auth/students/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: document.getElementById("student-name").value,
            email: document.getElementById("student-email").value,
            grade_level: document.getElementById("student-grade").value,
            password: document.getElementById("student-password").value,
          }),
        });
        const profile = await responseData(response);
        form.reset();
        renderProfile(profile);
        showMessage(accountMessage, "Student account created", "success");
      } catch (error) {
        showMessage(accountMessage, error.message, "error");
      }
    });

  document.getElementById("logout-button").addEventListener("click", async () => {
    try {
      const response = await fetch("/auth/logout", { method: "POST" });
      await responseData(response);
      accountProfile.classList.add("hidden");
      accountForms.classList.remove("hidden");
      profileMemberships.replaceChildren();
      profileSummary.textContent = "";
      showMessage(accountMessage, "Signed out", "success");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
    }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("email").value;
    const activity = activitySelect.value;

    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(activity)}/signup?email=${encodeURIComponent(email)}`,
        { method: "POST" }
      );
      const result = await responseData(response);
      showMessage(messageDiv, result.message, "success");
      signupForm.reset();
      await fetchActivities();
      await loadProfile();
    } catch (error) {
      showMessage(messageDiv, error.message, "error");
      console.error("Error signing up:", error);
    }
  });

  fetchActivities();
  loadProfile();
});
