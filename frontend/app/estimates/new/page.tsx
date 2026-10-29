"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Stepper } from "@/components/stepper";
import { useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";
import type { BuildingParams } from "@/lib/types";

type FormState = {
  project_name: string;
  location: string;
} & Omit<BuildingParams, "source">;

const DEFAULTS: FormState = {
  project_name: "",
  location: "Delhi",
  use_type: "hostel",
  plot_area_m2: 1800,
  builtup_area_m2: 3000,
  floors: 5,
  floor_height_m: 3.0,
  plan_shape: "rectangular",
  aspect_ratio: 1.5,
  structural_system: "rcc_framed",
  spec_level: "standard",
  sbc_kpa: 150,
};

const STEPS = [
  { id: "project", label: "Project" },
  { id: "geometry", label: "Building geometry" },
  { id: "structural", label: "Structure & spec" },
  { id: "review", label: "Review & run" },
];

export default function NewEstimatePage() {
  const router = useRouter();
  const toast = useToast();
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [stepId, setStepId] = useState<string>("project");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const stepIndex = STEPS.findIndex((s) => s.id === stepId);
  const canGoNext = stepIndex < STEPS.length - 1;
  const canGoBack = stepIndex > 0;
  const next = () => canGoNext && setStepId(STEPS[stepIndex + 1].id);
  const back = () => canGoBack && setStepId(STEPS[stepIndex - 1].id);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  async function onSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const project = await api.createProject({
        name: form.project_name,
        location: form.location,
        use_type: form.use_type,
      });
      const estimate = await api.createEstimate(project.id, {
        params: {
          use_type: form.use_type,
          plot_area_m2: form.plot_area_m2,
          builtup_area_m2: form.builtup_area_m2,
          floors: form.floors,
          floor_height_m: form.floor_height_m,
          plan_shape: form.plan_shape,
          aspect_ratio: form.aspect_ratio,
          structural_system: form.structural_system,
          spec_level: form.spec_level,
          sbc_kpa: form.sbc_kpa,
          location: form.location,
          source: "form",
        },
        cost_index: 1.0,
      });
      toast.success("Estimate created", "Running the engine now…");
      router.push(`/estimates/${estimate.id}/boq?autorun=1`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      setError(msg);
      toast.error("Couldn’t create estimate", msg);
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold">New estimate</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Describe the building. Takes under a minute.
        </p>
      </div>

      <div className="mb-8">
        <Stepper steps={STEPS} currentId={stepId} />
      </div>

      <Card>
        {stepId === "project" && <ProjectStep form={form} update={update} />}
        {stepId === "geometry" && <GeometryStep form={form} update={update} />}
        {stepId === "structural" && <StructuralStep form={form} update={update} />}
        {stepId === "review" && <ReviewStep form={form} />}

        {error && (
          <div className="mt-6 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
            {error}
          </div>
        )}

        <div className="mt-8 flex items-center justify-between">
          <Button variant="ghost" onClick={back} disabled={!canGoBack || submitting}>
            Back
          </Button>
          {canGoNext ? (
            <Button
              onClick={next}
              disabled={!stepValid(stepId, form)}
            >
              Continue
            </Button>
          ) : (
            <Button onClick={onSubmit} disabled={submitting || !stepValid("project", form)}>
              {submitting ? "Starting…" : "Create & run estimate"}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

function stepValid(stepId: string, f: FormState): boolean {
  if (stepId === "project") return f.project_name.trim().length > 0 && f.location.trim().length > 0;
  if (stepId === "geometry")
    return (
      f.plot_area_m2 > 0 &&
      f.builtup_area_m2 > 0 &&
      f.floors >= 1 &&
      f.floor_height_m >= 2.4 &&
      f.builtup_area_m2 <= f.plot_area_m2 * f.floors * 1.1
    );
  return true;
}

/* ------------------------------------------------------------------ steps */

function ProjectStep({
  form,
  update,
}: {
  form: FormState;
  update: <K extends keyof FormState>(k: K, v: FormState[K]) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="project_name">Project name</Label>
        <Input
          id="project_name"
          value={form.project_name}
          placeholder="e.g. Hostel block A"
          onChange={(e) => update("project_name", e.target.value)}
          autoFocus
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="location">Location (city)</Label>
          <Input
            id="location"
            value={form.location}
            onChange={(e) => update("location", e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="use_type">Use type</Label>
          <Select
            id="use_type"
            value={form.use_type}
            onChange={(e) => update("use_type", e.target.value as FormState["use_type"])}
          >
            <option value="residential">Residential</option>
            <option value="hostel">Hostel</option>
            <option value="office">Office</option>
            <option value="institutional">Institutional</option>
            <option value="commercial">Commercial</option>
            <option value="mixed_use">Mixed use</option>
          </Select>
        </div>
      </div>
    </div>
  );
}

function GeometryStep({
  form,
  update,
}: {
  form: FormState;
  update: <K extends keyof FormState>(k: K, v: FormState[K]) => void;
}) {
  const cap = form.plot_area_m2 * form.floors * 1.1;
  const overBuilt = form.builtup_area_m2 > cap;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <NumberField
          label="Plot area (m²)"
          value={form.plot_area_m2}
          onChange={(v) => update("plot_area_m2", v)}
          min={10}
          step={10}
        />
        <NumberField
          label="Built-up area, all floors (m²)"
          value={form.builtup_area_m2}
          onChange={(v) => update("builtup_area_m2", v)}
          min={10}
          step={10}
          invalid={overBuilt}
        />
      </div>
      {overBuilt && (
        <p className="text-xs text-red-600">
          Built-up {form.builtup_area_m2.toLocaleString("en-IN")} m² exceeds plot × floors × 1.1 ({cap.toLocaleString("en-IN")} m²).
        </p>
      )}
      <div className="grid grid-cols-2 gap-4">
        <NumberField label="Floors (incl. ground)" value={form.floors} onChange={(v) => update("floors", v)} min={1} max={20} step={1} />
        <NumberField label="Floor height (m)" value={form.floor_height_m} onChange={(v) => update("floor_height_m", v)} min={2.4} max={6} step={0.1} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Plan shape</Label>
          <Select value={form.plan_shape} onChange={(e) => update("plan_shape", e.target.value as FormState["plan_shape"])}>
            <option value="rectangular">Rectangular</option>
            <option value="l_shape">L-shape</option>
            <option value="square">Square</option>
            <option value="irregular">Irregular</option>
          </Select>
        </div>
        <NumberField label="Aspect ratio (L / B)" value={form.aspect_ratio} onChange={(v) => update("aspect_ratio", v)} min={0.4} max={3.5} step={0.1} />
      </div>
    </div>
  );
}

function StructuralStep({
  form,
  update,
}: {
  form: FormState;
  update: <K extends keyof FormState>(k: K, v: FormState[K]) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Structural system</Label>
          <Select
            value={form.structural_system}
            onChange={(e) => update("structural_system", e.target.value as FormState["structural_system"])}
          >
            <option value="rcc_framed">RCC framed</option>
            <option value="rcc_flat_slab">RCC flat slab</option>
            <option value="load_bearing">Load-bearing masonry (G+3 max)</option>
          </Select>
        </div>
        <div>
          <Label>Specification level</Label>
          <Select
            value={form.spec_level}
            onChange={(e) => update("spec_level", e.target.value as FormState["spec_level"])}
          >
            <option value="basic">Basic</option>
            <option value="standard">Standard</option>
            <option value="premium">Premium</option>
          </Select>
        </div>
      </div>
      <NumberField
        label="Soil bearing capacity (kPa)"
        value={form.sbc_kpa}
        onChange={(v) => update("sbc_kpa", v)}
        min={50}
        max={600}
        step={10}
      />
    </div>
  );
}

function ReviewStep({ form }: { form: FormState }) {
  const rows: Array<[string, string]> = [
    ["Project", form.project_name],
    ["Location", form.location],
    ["Use type", form.use_type],
    ["Plot area", `${form.plot_area_m2.toLocaleString("en-IN")} m²`],
    ["Built-up area", `${form.builtup_area_m2.toLocaleString("en-IN")} m²`],
    ["Floors × height", `${form.floors} × ${form.floor_height_m} m`],
    ["Plan shape · aspect", `${form.plan_shape} · ${form.aspect_ratio}`],
    ["Structural system", form.structural_system],
    ["Specification", form.spec_level],
    ["SBC", `${form.sbc_kpa} kPa`],
  ];
  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-500">
        Review the inputs. The engine will run and persist a priced BOQ you can edit on the next screen.
      </p>
      <dl className="divide-y divide-zinc-200 border border-zinc-200 rounded-md dark:divide-zinc-800 dark:border-zinc-800">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-3 px-4 py-2 text-sm">
            <dt className="text-zinc-500">{k}</dt>
            <dd className="col-span-2 font-medium">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  invalid,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  invalid?: boolean;
}) {
  return (
    <div>
      <Label>{label}</Label>
      <Input
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className={invalid ? "border-red-500 focus-visible:ring-red-500" : ""}
      />
    </div>
  );
}
