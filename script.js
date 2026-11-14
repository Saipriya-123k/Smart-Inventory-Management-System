document.addEventListener("DOMContentLoaded", function () {
  const canvas = document.getElementById("salesChart");
  if (canvas && window.Chart) {
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: window.salesLabels || [],
        datasets: [{
          label: "Sales revenue (₹)",
          data: window.salesValues || [],
          backgroundColor: "#55ad7d",
          borderRadius: 7,
          maxBarThickness: 42
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, grid: { color: "#edf1ee" } }, x: { grid: { display: false } } }
      }
    });
  }
});
