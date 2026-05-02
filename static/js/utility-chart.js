const payload = window.chartPayload;
const elecUsageTrimmed = payload.elec_usage.slice(1);
const gasUsageTrimmed = payload.gas_usage.slice(1);
const datesTrimmed = payload.dates.slice(1);
const cutoff = new Date();
cutoff.setDate(cutoff.getDate() - 30);


// LOAD CSS VARIABLES
const styles = getComputedStyle(document.documentElement);
const warningColor = styles.getPropertyValue('--warning-color').trim();
const buttonColor = styles.getPropertyValue('--button-color').trim();


// Raw arrays
const dates = payload.dates || [];
const elecUsage = payload.elec_usage || [];
const gasUsage = payload.gas_usage || [];
const elecBal = payload.elec_balance || [];
const gasBal = payload.gas_balance || [];
const topups = payload.topup_points || [];
const elecTopup30 = topups
  .filter(t => t.meter === 'electricity' && new Date(t.date) >= cutoff)
  .map(t => ({ x: t.date, y: t.amount }));

const gasTopup30 = topups
  .filter(t => t.meter === 'gas' && new Date(t.date) >= cutoff)
  .map(t => ({ x: t.date, y: t.amount }));


// ------------------ CONSUMPTION CHART ------------------
const ctxC = document.getElementById('consumptionChart').getContext('2d');

const consumptionChart = new Chart(ctxC, {
  type: 'line',
  data: {
    labels: datesTrimmed,
    datasets: [
      {
        label: 'Electricity (units)',
        data: elecUsageTrimmed,
        borderColor: warningColor,     // <-- FIXED
        borderWidth: 2,
        tension: 0.3,                  // <-- smoother curve
        fill: false,
        pointRadius: 3,
      },
      {
        label: 'Gas (units)',
        data: gasUsageTrimmed,
        borderColor: buttonColor,      // use theme color
        borderWidth: 2,
        tension: 0.3,
        fill: false,
        pointRadius: 3,
      }
    ]
  },
  options: {
    responsive: true,
    scales: { y: { beginAtZero: true } },
    plugins: {
      legend: {
        position: 'top',
        labels: { boxWidth: 20, pointStyle: 'line', usePointStyle: true }
      },
      tooltip: {
        bodyFont: { family: 'Gotu', size: 11 },
        titleFont: { family: 'Gotu', size: 13 }
      }
    }
  }
});


// ------------------ BALANCE CHART ------------------
const ctxB = document.getElementById('balanceChart') ? document.getElementById('balanceChart').getContext('2d') : document.getElementById('topupChart').getContext('2d');
const balanceChart = new Chart(ctxB, {
  type: 'line',
  data: {
    labels: dates,   // use raw dates to align with raw readings
    datasets: [
      {
        label: 'Electricity Balance',
        data: payload.elec_readings,
        borderColor: warningColor,
        borderWidth: 2,
        tension: 0.3,
        fill: false
      },
      {
        label: 'Gas Balance',
        data: payload.gas_readings,
        borderColor: buttonColor,
        borderWidth: 2,
        tension: 0.3,
        fill: false
      },
      {
        label: 'Top-ups (Electricity)',
        data: elecTopup30,
        type: 'scatter',
        pointBackgroundColor: warningColor,
        pointRadius: 6
      },
      {
        label: 'Top-ups (Gas)',
        data: gasTopup30,
        type: 'scatter',
        pointBackgroundColor: buttonColor,
        pointRadius: 6
      }
    ]
  },
  options: {
    responsive: true,
    scales: {
      x: {
        type: 'time',
        time: { parser: 'yyyy-MM-dd', unit: 'day' }
      },
      y: { beginAtZero: true }
    },
    plugins: {
      legend: {
        position: 'top',
        labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 8, boxHeight: 8 }
      }
    }
  }
});


// ------------------ TOGGLES ------------------


document.getElementById('showBalance').addEventListener('change', (e) => {
  const show = e.target.checked;
  const balanceCanvas = document.getElementById('balanceChart');

  if (show) {
    balanceCanvas.style.display = 'block';
    // Small timeout allows display:block to apply so the fade-in plays
    setTimeout(() => {
      balanceCanvas.classList.add('visible');
      balanceChart.update();
    }, 10);
  } else {
    balanceCanvas.classList.remove('visible');
    // Hide after fade-out transition (400ms) completes
    setTimeout(() => {
      if (!document.getElementById('showBalance').checked) {
        balanceCanvas.style.display = 'none';
      }
    }, 400);
  }
});


