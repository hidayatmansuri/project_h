const payload = window.chartPayload;

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
const topups = payload.topups || [];

// ------------------ CONSUMPTION CHART ------------------
const ctxC = document.getElementById('consumptionChart').getContext('2d');

const consumptionChart = new Chart(ctxC, {
  type: 'line',
  data: {
    labels: dates,
    datasets: [
      {
        label: 'Electricity (units)',
        data: elecUsage,
        borderColor: warningColor,     // <-- FIXED
        borderWidth: 2,
        tension: 0.3,                  // <-- smoother curve
        fill: false,
        pointRadius: 3,
      },
      {
        label: 'Gas (units)',
        data: gasUsage,
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
    scales: { y: { beginAtZero: false } },
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
const balanceChart = new Chart(ctxB, {
  type: 'line',
  data: {
    labels: dates,
    datasets: [
      {
        label:'Electricity Balance',
        data: elecBal,
        borderColor: warningColor,
        borderWidth: 2,
        tension: 0.3,
        fill:false
      },
      {
        label:'Gas Balance',
        data: gasBal,
        borderColor: buttonColor,
        borderWidth: 2,
        tension: 0.3,
        fill:false
      },
      {
        label:'Top-ups (Electricity)',
        data: topups.filter(t => t.meter==='electricity').map(t => ({ x:t.date, y: 0 })),
        type:'scatter',
        pointBackgroundColor: warningColor,
        pointRadius:6
      },
      {
        label:'Top-ups (Gas)',
        data: topups.filter(t => t.meter==='gas').map(t => ({ x:t.date, y: 0 })),
        type:'scatter',
        pointBackgroundColor: buttonColor,
        pointRadius:6
      }
    ]
  },
  options: {
    responsive:true,
    scales: {
      x: {
        type:'time',
        time: { parser:'yyyy-MM-dd', unit:'day' }
      },
      y: { beginAtZero:false }
    },
    plugins: { legend:{ position:'top' } }
  }
});


// ------------------ TOGGLES ------------------

document.getElementById('showBalance').addEventListener('change', (e) => {
  const show = e.target.checked;
  const balanceCanvas = document.getElementById('balanceChart');
  balanceCanvas.style.display = show ? 'block' : 'none';

  if (show) {
    balanceChart.update();
  }
});


