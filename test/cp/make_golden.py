# Regenerate golden_frames.txt after a deliberate change to the screens.
# Look at the frames before keeping them.
import scenario

with open(scenario.GOLDEN, "w") as f:
    f.write(scenario.render_text())
print(open(scenario.GOLDEN).read())
