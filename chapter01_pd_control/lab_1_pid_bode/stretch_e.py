from starter import LAB_DIR, PDGains, default_gains, run_bode_sweep
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter
from shared.viz.plot_utils import apply_theme

base_gains,inertia = default_gains()
kp_values=[base_gains.kp,2*base_gains.kp,5*base_gains.kp]
print(kp_values)
results={}
for kp in kp_values:
    gains=PDGains(kp=kp,kd=base_gains.kd)
    points=run_bode_sweep(gains=gains,inertia=inertia)
    results[kp]=points
    print(f'Kp={kp},频点数={len(points)}')

apply_theme()
fig, (ax_gain, ax_phase) = plt.subplots(
    2, 1, figsize=(8.5, 6.2), sharex=True
)
for kp, points in results.items():
    frequencies = [point.frequency_hz for point in points]
    gain_db=[point.gain_db for point in points]
    phase_deg=[point.phase_deg for point in points]
    print(kp, gain_db)
    ax_gain.semilogx(frequencies, gain_db, "o-", label=f"Kp={kp:g}")
    ax_phase.semilogx(frequencies, phase_deg, "o-", label=f"Kp={kp:g}")
    
ax_gain.axhline(-3, color="red", linestyle="--")
ax_gain.set_ylabel("增益 (dB)")
ax_phase.set_ylabel("相位差 (°)")
ax_phase.set_xlabel("频率 (Hz)")
ax_phase.set_xticks(frequencies, labels=[f"{f:g}" for f in frequencies])
ax_phase.xaxis.set_minor_formatter(NullFormatter())
ax_gain.legend()
ax_phase.legend()

fig.suptitle(f"Kp 对比，固定 Kd={base_gains.kd:.4f}")
fig.tight_layout()

output_path = LAB_DIR / "portfolio" / "bode_kp_comparison.png"
fig.savefig(output_path, dpi=150)
plt.close(fig)
print(output_path)