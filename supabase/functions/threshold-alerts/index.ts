// Supabase Edge Function: threshold-alerts
// Checks device metrics and creates alerts for devices exceeding thresholds.
// Schedule: every 5 minutes via Supabase Cron.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const THRESHOLDS = {
  cpu_usage: { warning: 85, critical: 95 },
  ram_usage: { warning: 85, critical: 95 },
  storage_free_warning_gb: 10,
  storage_free_critical_gb: 5,
  offline_minutes: 5,
};

Deno.serve(async () => {
  const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

  const { data: devices, error } = await supabase
    .from("devices")
    .select("id, hostname, display_name, status, last_seen, cpu_usage, ram_usage, storage_free, is_approved")
    .eq("is_approved", true);

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }

  const now = new Date();
  const alerts: {
    device_id: string;
    severity: "warning" | "critical";
    message: string;
  }[] = [];

  for (const d of devices ?? []) {
    const name = d.display_name ?? d.hostname;

    // CPU
    if (d.cpu_usage >= THRESHOLDS.cpu_usage.critical) {
      alerts.push({ device_id: d.id, severity: "critical", message: `CPU usage ${d.cpu_usage.toFixed(0)}% (critical threshold ${THRESHOLDS.cpu_usage.critical}%) on ${name}` });
    } else if (d.cpu_usage >= THRESHOLDS.cpu_usage.warning) {
      alerts.push({ device_id: d.id, severity: "warning", message: `CPU usage ${d.cpu_usage.toFixed(0)}% (warning threshold ${THRESHOLDS.cpu_usage.warning}%) on ${name}` });
    }

    // RAM
    if (d.ram_usage >= THRESHOLDS.ram_usage.critical) {
      alerts.push({ device_id: d.id, severity: "critical", message: `RAM usage ${d.ram_usage.toFixed(0)}% (critical threshold ${THRESHOLDS.ram_usage.critical}%) on ${name}` });
    } else if (d.ram_usage >= THRESHOLDS.ram_usage.warning) {
      alerts.push({ device_id: d.id, severity: "warning", message: `RAM usage ${d.ram_usage.toFixed(0)}% (warning threshold ${THRESHOLDS.ram_usage.warning}%) on ${name}` });
    }

    // Storage free
    if (d.storage_free != null) {
      const freeGb = d.storage_free / 1_073_741_824;
      if (freeGb < THRESHOLDS.storage_free_critical_gb) {
        alerts.push({ device_id: d.id, severity: "critical", message: `Disk free ${freeGb.toFixed(1)} GB (critical < ${THRESHOLDS.storage_free_critical_gb} GB) on ${name}` });
      } else if (freeGb < THRESHOLDS.storage_free_warning_gb) {
        alerts.push({ device_id: d.id, severity: "warning", message: `Disk free ${freeGb.toFixed(1)} GB (warning < ${THRESHOLDS.storage_free_warning_gb} GB) on ${name}` });
      }
    }

    // Offline detection
    if (d.status === "online" && d.last_seen) {
      const lastSeen = new Date(d.last_seen);
      const minutesAgo = (now.getTime() - lastSeen.getTime()) / 60_000;
      if (minutesAgo > THRESHOLDS.offline_minutes) {
        alerts.push({ device_id: d.id, severity: "warning", message: `Device ${name} appears offline (last seen ${minutesAgo.toFixed(0)}m ago)` });
      }
    }
  }

  // Deduplicate: don't insert if an unresolved alert with same device_id + message already exists
  if (alerts.length > 0) {
    const deviceIds = [...new Set(alerts.map((a) => a.device_id))];
    const { data: existing } = await supabase
      .from("alerts_log")
      .select("device_id, message")
      .in("device_id", deviceIds)
      .eq("is_resolved", false);

    const existingSet = new Set((existing ?? []).map((e) => `${e.device_id}:${e.message}`));
    const newAlerts = alerts.filter((a) => !existingSet.has(`${a.device_id}:${a.message}`));

    if (newAlerts.length > 0) {
      await supabase.from("alerts_log").insert(newAlerts);
    }

    return new Response(JSON.stringify({ checked: (devices ?? []).length, new_alerts: newAlerts.length }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ checked: (devices ?? []).length, new_alerts: 0 }), {
    headers: { "Content-Type": "application/json" },
  });
});
