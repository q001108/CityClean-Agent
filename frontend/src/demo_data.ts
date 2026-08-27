import fixture_data from "../fixtures/vehicle_breakdown_replan.json";
import v2_fixture_data from "../fixtures/complaint_urgent_v2.json";
import type { FrontendFixture, V2ExperienceFixture } from "./types";

const demo_scenario: FrontendFixture = fixture_data;
const v2_experience: V2ExperienceFixture = v2_fixture_data;

export function load_demo_scenario(): FrontendFixture {
  if (demo_scenario.frames.length === 0) {
    throw new Error("The demo fixture does not contain any frames.");
  }

  if (demo_scenario.timeline.length !== demo_scenario.frames.length) {
    throw new Error("The demo fixture timeline and frame counts do not match.");
  }

  return demo_scenario;
}

export function load_v2_experience(): V2ExperienceFixture {
  if (v2_experience.schema_version !== "2.0") {
    throw new Error("The v2 experience fixture has an unexpected schema version.");
  }
  return v2_experience;
}
