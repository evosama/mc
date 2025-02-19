// Function to start the report generation process
function startReportGeneration() {
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");
    const generateButton = document.getElementById("generate-report-btn");
    const regenerateButton = document.getElementById("regenerate-report-btn");
    const reportFrame = document.getElementById("report-frame");
    const eventSource = new EventSource('/progress/');
    const logArea = document.getElementById('log-area');

    // Reset and display progress elements
    progressBar.parentElement.style.display = "block";
    progressText.style.display = "block";
    generateButton.disabled = true;
    regenerateButton.style.display = "none";
    reportFrame.src = ""; // Clear previous report

    // Trigger backend report generation
    fetch('/generate_report/', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error("Error starting report generation.");
            }

            eventSource.onmessage = function(event) {
                const logEntry = document.createElement('div');
                logEntry.textContent = event.data;
                logArea.appendChild(logEntry);
                logArea.scrollTop = logArea.scrollHeight;  // Auto-scroll to the bottom
            };
            
            eventSource.onerror = function() {
                console.error("Connection lost.");
                eventSource.close();
            };

        })
        .catch(error => {
            console.error("Error initiating report generation:", error);
            progressText.innerText = "Error during report generation.";
            generateButton.disabled = false;
        });
}
