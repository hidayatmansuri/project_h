const payload = window.chartPayload;

// Raw arrays
const dates = payload.dates || [];
const elecUsage = payload.elec_usage || [];
const gasUsage = payload.gas_usage || [];
const elecBal = payload.elec_balance || [];
const gasBal = payload.gas_balance || [];
const topups = payload.topups || [];

// consumption chart
const ctxC = document.getElementById('consumptionChart').getContext('2d');
const consumptionChart = new Chart(ctxC, {
  type: 'line',
  data: {
    labels: dates,
    datasets: [
      { label: 'Electricity (units)', data: elecUsage, borderColor: '#FFD056', fill:false, tension:0.1 },
      { label: 'Gas (units)', data: gasUsage, borderColor: '#4BC0C0', fill:false, tension:0.3 }
    ]
  },
  options: {
    responsive: true,
    scales:{ y:{ beginAtZero:true } },
    plugins:{ legend:{ position:'top' } }
  }
});

// balance chart
const ctxB = document.getElementById('balanceChart').getContext('2d');
const balanceChart = new Chart(ctxB, {
  type: 'line',
  data: {
    labels: dates,
    datasets: [
      { label:'Electricity Balance', data: elecBal, borderColor:'#FF8A65', fill:false, tension:0.3 },
      { label:'Gas Balance', data: gasBal, borderColor:'#90A4AE', fill:false, tension:0.3 },
      { label:'Top-ups (Electricity)', data: topups.filter(t => t.meter==='electricity').map(t => ({ x:t.date, y: 0 })), type:'scatter', pointBackgroundColor:'#FF8A65', pointRadius:6 },
      { label:'Top-ups (Gas)', data: topups.filter(t => t.meter==='gas').map(t => ({ x:t.date, y: 0 })), type:'scatter', pointBackgroundColor:'#90A4AE', pointRadius:6 }
    ]
  },
  options: {
    responsive:true,
    scales: { x: { type:'time', time: { parser:'yyyy-MM-dd', unit:'day' } }, y: { beginAtZero:false } },
    plugins: { legend:{ position:'top' } }
  }
});

// toggles
document.querySelectorAll('input[name="viewMode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    consumptionChart.update();
    balanceChart.update();
  });
});

document.getElementById('showBalance').addEventListener('change', (e) => {
  const show = e.target.checked;
  document.getElementById('balanceChart').style.display = show ? 'block' : 'none';
});
