import numpy as np
from matching import circular_residual
from position_loss import CAP_HZ, SCALE_HZ, best_group_rows, rho


def interpolate_states(nodes, positions, velocities, times, shifts):
    query = times[:, None] + shifts[None, :]
    if np.any(query < nodes[0]) or np.any(query >= nodes[-1]):
        raise ValueError("time query outside state grid")
    step = nodes[1] - nodes[0]
    fractional = (query - nodes[0]) / step
    lower = np.floor(fractional).astype(int)
    fraction = (fractional - lower)[..., None]
    satellites = np.arange(len(shifts))[None, :]
    position_left = positions[satellites, lower]
    velocity_left = velocities[satellites, lower]
    position_delta = positions[satellites, lower + 1] - position_left
    velocity_delta = velocities[satellites, lower + 1] - velocity_left
    return (
        position_left + fraction * position_delta,
        velocity_left + fraction * velocity_delta,
        position_delta / step,
        velocity_delta / step,
    )


def gaussian_prior(shifts, sigma):
    if sigma <= 0:
        raise ValueError("prior sigma must be positive")
    return float(0.5 * np.sum((shifts / sigma) ** 2)), shifts / sigma**2


class TimeShiftObjective:
    def __init__(self, data, states, correction, site, sigma=1.0):
        self.data = {key: np.asarray(data[key]) for key in ("times", "rf", "measured", "group")}
        self.states = {key: np.asarray(states[key]) for key in ("nodes", "position", "velocity")}
        self.correction = correction
        self.site = site
        self.sigma = sigma
        self.calls = 0

    def evaluate(self, parameters, details=False):
        self.calls += 1
        receiver, up = self.site(parameters[:2])
        position, velocity, position_rate, acceleration = interpolate_states(
            self.states["nodes"],
            self.states["position"],
            self.states["velocity"],
            self.data["times"],
            parameters[2:],
        )
        delta = position - receiver
        distance = np.linalg.norm(delta, axis=-1)
        direction = delta / distance[..., None]
        radial_velocity = np.sum(direction * velocity, axis=-1)
        rf_scale = self.data["rf"] / 299792.458
        prediction = -rf_scale[:, None] * radial_velocity + self.correction[:, None]
        residual = circular_residual(self.data["measured"][:, None], prediction)
        residual[np.sum(direction * up, axis=-1) < 0] = np.inf
        rows, satellites, errors = best_group_rows(residual, self.data["group"])
        data_loss = float(np.sum(rho(errors)) / (2 * SCALE_HZ**2))
        prior, prior_gradient = gaussian_prior(parameters[2:], self.sigma)
        value = data_loss + prior
        derivative = np.zeros(len(rows))
        active = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
        derivative[active] = (
            errors[active] / SCALE_HZ**2 / np.sqrt(1 + (errors[active] / SCALE_HZ) ** 2)
        )
        unit = direction[rows, satellites]
        speed = velocity[rows, satellites]
        range_rate = radial_velocity[rows, satellites]
        ranges = distance[rows, satellites]
        gradient_prediction_ecef = (
            rf_scale[rows, None] * (speed - unit * range_rate[:, None]) / ranges[:, None]
        )
        position_jacobian = np.zeros((3, 2))
        for coordinate in range(2):
            step = np.zeros(2)
            step[coordinate] = 0.001
            plus, _ = self.site(parameters[:2] + step)
            minus, _ = self.site(parameters[:2] - step)
            position_jacobian[:, coordinate] = (plus - minus) / 0.002
        gradient_position = (
            -np.sum(derivative[:, None] * gradient_prediction_ecef, axis=0) @ position_jacobian
        )
        motion = position_rate[rows, satellites]
        direction_rate = (motion - unit * np.sum(unit * motion, axis=1)[:, None]) / ranges[:, None]
        radial_acceleration = np.sum(
            direction_rate * speed + unit * acceleration[rows, satellites], axis=1
        )
        gradient_time = (
            np.bincount(
                satellites,
                weights=derivative * rf_scale[rows] * radial_acceleration,
                minlength=len(parameters) - 2,
            )
            + prior_gradient
        )
        gradient = np.r_[gradient_position, gradient_time]
        if not details:
            return value, gradient
        return {
            "penalized_objective": value,
            "data_objective": data_loss,
            "gaussian_penalty": prior,
            "mean_frequency_loss": float(np.mean(rho(errors))),
            "groups": len(rows),
            "groups_within_1000hz": int(np.sum(np.abs(errors) < 1000)),
            "assignment_counts": np.bincount(satellites, minlength=len(parameters) - 2).tolist(),
            "gradient": gradient.tolist(),
        }
