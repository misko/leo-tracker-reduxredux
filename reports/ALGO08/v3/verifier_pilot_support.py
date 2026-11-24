"""Relink the original two-scan and 8 ms receivers with scoped verifier staging."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from .cross_lag_eight_ms import BUILD_SHA, EIGHT, EIGHT_SHA, VERIFIER_SHA
from .directed_verifier_trial import replace_once
from .mixed_aperture_receiver import INSTALLED_SHA, verified
from .mixed_aperture_trial import exports
from .scout_readout_trial import check_machine
from .whole_group_receiver_bound import FULL_BUILD, FULL_BUILD_SHA


HERE = Path(__file__).resolve().parent
FULL_PIN = "4f0f48afe10f637be341add3763c42e57fcecdc7651260c3defcc19fc1104ca1"
FULL_VERIFY = "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707"
SHORT_VERIFY = "bae3798db85b2682ae88d7ce545aac0d084c5f3a747d34cf5c43edd908e0996b"
SHORT_WRAPPER = "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e"
STENCILS = {"full": "cc8128035f99faa0ce9b45482d7db9278c5c0d1713879fc7a271b2a37f47a957",
            "short": "8b2f4162d9637991e45b3e47eea28aadd9ff254bee02389569be69180f064a63"}
HELPER = HERE / "verifier_pilot_support.inc"
SUPPORT = ("portable_verifier_load_support", "portable_verifier_support_counts")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def wrapper_source(text, short):
    marker = "static int measure(TwoCarrierReceiver *r"
    helper = """int portable_verifier_load_support(PortableVerifier *, const int16_t *, unsigned, unsigned, unsigned);

static unsigned verifier_epoch(const TimingFirstResult *peak) {
    return (unsigned)nearbyint(peak->epoch) % period;
}

"""
    text = replace_once(text, marker, helper + marker)
    text = replace_once(text, "if (status || portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;",
                        "if (status || portable_verifier_load_support(r->verify, iq, (unsigned)lane,\n"
                        "        verifier_epoch(&p[0]), p[1].confirmation ? verifier_epoch(&p[1]) : period)) return -1;")
    if short:
        text = replace_once(text, "if (portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;",
                            "if (portable_verifier_load_support(r->verify, iq, (unsigned)lane,\n"
                            "                                  verifier_epoch(&scouts[0]), period)) return -1;")
    return text


def build(root):
    from .eight_ms_primary import write
    from .live_stereo_0008 import original
    from .scout_readout_trial import SOURCE_SHA

    machine = check_machine()
    install = original.PAYLOAD / "receiver.so"
    verified(install, INSTALLED_SHA)
    verified(EIGHT, EIGHT_SHA)
    full = json.loads(verified(FULL_BUILD, FULL_BUILD_SHA))
    short = json.loads(verified(EIGHT.with_name("build-receipt.json"), BUILD_SHA))
    if subprocess.check_output(["cc", "--version"], text=True).splitlines()[0] != full["compiler"]:
        raise ValueError("The archived native compiler differs")
    root.mkdir()
    commands, objects = {}, {}
    for mode, release, pin, recipe in (("full", install, INSTALLED_SHA, full["commands"][-1]),
                                       ("short", EIGHT, EIGHT_SHA, short["relink"])):
        stage = root / mode
        stage.mkdir()
        commands[mode] = []

        def run(argv):
            command = list(map(str, argv))
            commands[mode].append(command)
            subprocess.run(command, cwd=full["cwd"], check=True)

        control = stage / "control.so"
        run([*recipe[:-1], control])
        verified(control, pin)
        wrapper = next(Path(arg) for arg in recipe if Path(arg).name == "two_carrier_receiver.o")
        verifier = next(Path(arg) for arg in recipe if Path(arg).name == "portable_verifier.o")
        short_mode = mode == "short"
        verified(verifier, VERIFIER_SHA if short_mode else FULL_PIN)
        wrapper_c = verified(wrapper.with_suffix(".c"), SHORT_WRAPPER if short_mode else SOURCE_SHA)
        verifier_c = verified(verifier.with_suffix(".c"), SHORT_VERIFY if short_mode else FULL_VERIFY)
        wrapper_new, verifier_new = (stage / f"{name}.c" for name in ("two_carrier_receiver", "portable_verifier"))
        wrapper_new.write_text(wrapper_source(wrapper_c.decode(), short_mode))
        loaded, frames = ("loaded_samples", "analysis_frames") if short_mode else ("samples", "max_frames")
        verifier_new.write_bytes(verifier_c + (f'\n#define SUPPORT_LOADED_SAMPLES {loaded}\n'
                                              f'#define SUPPORT_ANALYSIS_FRAMES {frames}\n'
                                              f'#include "{HELPER.name}"\n').encode())
        compiler = full["commands"][-2]
        stencil = verifier.parent if short_mode else Path(compiler[-5])
        name = "receiver_stencil_verify.inc"
        (stage / name).write_bytes(verified(stencil / name, STENCILS[mode]))
        wrapper_flags = short["compile"][:-4] if short_mode else compiler[:-4]
        run([*wrapper_flags, "-Wall", "-Werror", "-c", wrapper_new, "-o", wrapper_new.with_suffix(".o")])
        run([*compiler[:-4], "-I", HERE, "-Wall", "-Werror", "-c", verifier_new, "-o", verifier_new.with_suffix(".o")])
        binary = stage / "support.so"
        substitutions = {str(old): stage / old.name for old in (wrapper, verifier)}
        run([*(substitutions.get(arg, arg) for arg in recipe[:-1]), binary])
        if exports(binary) != exports(release) | set(SUPPORT):
            raise ValueError("The original receiver ABI or native symbol inventory changed")
        objects[mode] = dict(candidate=digest(binary), control=pin,
                             wrapper=digest(wrapper_new), verifier=digest(verifier_new),
                             stencil=STENCILS[mode])
    write(root / "build.json", dict(binaries=objects, commands=commands, machine=machine,
                                  source_sha256=digest(Path(__file__)), support_sha256=digest(HELPER),
                                  bindings={str(FULL_BUILD): FULL_BUILD_SHA,
                                            str(EIGHT.with_name("build-receipt.json")): BUILD_SHA}))


if __name__ == "__main__":
    build(Path(sys.argv[1]))
