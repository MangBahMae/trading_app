// 회귀 방지: "0이 안 지워지고, 100을 입력하면 0100이 된다"는 실제 버그 리포트를
// 그대로 재현해서 검증한다.
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import NumberInput from "./NumberInput";

function Harness() {
  const [value, setValue] = useState(0);
  return <NumberInput id="n" value={value} onChange={setValue} />;
}

describe("NumberInput", () => {
  it("전부 지우면 실제로 빈 칸이 된다 (강제로 0이 다시 채워지지 않음)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;

    expect(input.value).toBe("0");
    await user.clear(input);
    expect(input.value).toBe("");
  });

  it("지운 뒤 100을 입력하면 0100이 아니라 100이 된다", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;

    await user.clear(input);
    await user.type(input, "100");
    expect(input.value).toBe("100");
  });

  it("외부에서 value가 바뀌면(예: 계산기로 채우기) 표시 텍스트도 갱신된다", () => {
    const { rerender } = render(<NumberInput id="n" value={0} onChange={() => {}} />);
    const input = screen.getByRole("spinbutton") as HTMLInputElement;
    expect(input.value).toBe("0");

    rerender(<NumberInput id="n" value={118000} onChange={() => {}} />);
    expect(input.value).toBe("118000");
  });
});
