import warnings
from collections import namedtuple
import operator
from . import _zeros
from ._optimize import OptimizeResult, _call_callback_maybe_halt
import numpy as np


_iter = 100
_xtol = 2e-12
_rtol = 4 * np.finfo(float).eps

__all__ = ['newton', 'bisect', 'ridder', 'brentq', 'brenth', 'toms748',
           'RootResults']

# Must agree with CONVERGED, SIGNERR, CONVERR, ...  in zeros.h
_ECONVERGED = 0
_ESIGNERR = -1
_ECONVERR = -2
_EVALUEERR = -3
_ECALLBACK = -4
_EINPROGRESS = 1

CONVERGED = 'converged'
SIGNERR = 'sign error'
CONVERR = 'convergence error'
VALUEERR = 'value error'
INPROGRESS = 'No error'


flag_map = {_ECONVERGED: CONVERGED, _ESIGNERR: SIGNERR, _ECONVERR: CONVERR,
            _EVALUEERR: VALUEERR, _EINPROGRESS: INPROGRESS}


class RootResults(OptimizeResult):
    """Represents the root finding result.

    Attributes
    ----------
    root : float
        Estimated root location.
    iterations : int
        Number of iterations needed to find the root.
    function_calls : int
        Number of times the function was called.
    converged : bool
        True if the routine converged.
    flag : str
        Description of the cause of termination.

    """

    def __init__(self, root, iterations, function_calls, flag):
        self.root = root
        self.iterations = iterations
        self.function_calls = function_calls
        self.converged = flag == _ECONVERGED
        if flag in flag_map:
            self.flag = flag_map[flag]
        else:
            self.flag = flag


def results_c(full_output, r):
    if full_output:
        x, funcalls, iterations, flag = r
        results = RootResults(root=x,
                              iterations=iterations,
                              function_calls=funcalls,
                              flag=flag)
        return x, results
    else:
        return r


def _results_select(full_output, r):
    """Select from a tuple of (root, funccalls, iterations, flag)"""
    x, funcalls, iterations, flag = r
    if full_output:
        results = RootResults(root=x,
                              iterations=iterations,
                              function_calls=funcalls,
                              flag=flag)
        return x, results
    return x


def _wrap_nan_raise(f):

    def f_raise(x, *args):
        fx = f(x, *args)
        f_raise._function_calls += 1
        if np.isnan(fx):
            msg = (f'The function value at x={x} is NaN; '
                   'solver cannot continue.')
            err = ValueError(msg)
            err._x = x
            err._function_calls = f_raise._function_calls
            raise err
        return fx

    f_raise._function_calls = 0
    return f_raise


def newton(func, x0, fprime=None, args=(), tol=1.48e-8, maxiter=50,
           fprime2=None, x1=None, rtol=0.0,
           full_output=False, disp=True):
    """
    Find a root of a real or complex function using the Newton-Raphson
    (or secant or Halley's) method.

    Find a root of the scalar-valued function `func` given a nearby scalar
    starting point `x0`.
    The Newton-Raphson method is used if the derivative `fprime` of `func`
    is provided, otherwise the secant method is used. If the second order
    derivative `fprime2` of `func` is also provided, then Halley's method is
    used.

    If `x0` is a sequence with more than one item, `newton` returns an array:
    the roots of the function from each (scalar) starting point in `x0`.
    In this case, `func` must be vectorized to return a sequence or array of
    the same shape as its first argument. If `fprime` (`fprime2`) is given,
    then its return must also have the same shape: each element is the first
    (second) derivative of `func` with respect to its only variable evaluated
    at each element of its first argument.

    `newton` is for finding roots of a scalar-valued functions of a single
    variable. For problems involving several variables, see `root`.

    Parameters
    ----------
    func : callable
        The function whose root is wanted. It must be a function of a
        single variable of the form ``f(x,a,b,c...)``, where ``a,b,c...``
        are extra arguments that can be passed in the `args` parameter.
    x0 : float, sequence, or ndarray
        An initial estimate of the root that should be somewhere near the
        actual root. If not scalar, then `func` must be vectorized and return
        a sequence or array of the same shape as its first argument.
    fprime : callable, optional
        The derivative of the function when available and convenient. If it
        is None (default), then the secant method is used.
    args : tuple, optional
        Extra arguments to be used in the function call.
    tol : float, optional
        The allowable error of the root's value. If `func` is complex-valued,
        a larger `tol` is recommended as both the real and imaginary parts
        of `x` contribute to ``|x - x0|``.
    maxiter : int, optional
        Maximum number of iterations.
    fprime2 : callable, optional
        The second order derivative of the function when available and
        convenient. If it is None (default), then the normal Newton-Raphson
        or the secant method is used. If it is not None, then Halley's method
        is used.
    x1 : float, optional
        Another estimate of the root that should be somewhere near the
        actual root. Used if `fprime` is not provided.
    rtol : float, optional
        Tolerance (relative) for termination.
    full_output : bool, optional
        If `full_output` is False (default), the root is returned.
        If True and `x0` is scalar, the return value is ``(x, r)``, where ``x``
        is the root and ``r`` is a `RootResults` object.
        If True and `x0` is non-scalar, the return value is ``(x, converged,
        zero_der)`` (see Returns section for details).
    disp : bool, optional
        If True, raise a RuntimeError if the algorithm didn't converge, with
        the error message containing the number of iterations and current
        function value. Otherwise, the convergence status is recorded in a
        `RootResults` return object.
        Ignored if `x0` is not scalar.
        *Note: this has little to do with displaying, however,
        the `disp` keyword cannot be renamed for backwards compatibility.*

    Returns
    -------
    root : float, sequence, or ndarray
        Estimated location where function is zero.
    r : `RootResults`, optional
        Present if ``full_output=True`` and `x0` is scalar.
        Object containing information about the convergence. In particular,
        ``r.converged`` is True if the routine converged.
    converged : ndarray of bool, optional
        Present if ``full_output=True`` and `x0` is non-scalar.
        For vector functions, indicates which elements converged successfully.
    zero_der : ndarray of bool, optional
        Present if ``full_output=True`` and `x0` is non-scalar.
        For vector functions, indicates which elements had a zero derivative.

    See Also
    --------
    root_scalar : interface to root solvers for scalar functions
    root : interface to root solvers for multi-input, multi-output functions

    Notes
    -----
    The convergence rate of the Newton-Raphson method is quadratic,
    the Halley method is cubic, and the secant method is
    sub-quadratic. This means that if the function is well-behaved
    the actual error in the estimated root after the nth iteration
    is approximately the square (cube for Halley) of the error
    after the (n-1)th step. However, the stopping criterion used
    here is the step size and there is no guarantee that a root
    has been found. Consequently, the result should be verified.
    Safer algorithms are brentq, brenth, ridder, and bisect,
    but they all require that the root first be bracketed in an
    interval where the function changes sign. The brentq algorithm
    is recommended for general use in one dimensional problems
    when such an interval has been found.

    When `newton` is used with arrays, it is best suited for the following
    types of problems:

    * The initial guesses, `x0`, are all relatively the same distance from
      the roots.
    * Some or all of the extra arguments, `args`, are also arrays so that a
      class of similar problems can be solved together.
    * The size of the initial guesses, `x0`, is larger than O(100) elements.
      Otherwise, a naive loop may perform as well or better than a vector.

    Examples
    --------
    >>> import numpy as np
    >>> import matplotlib.pyplot as plt
    >>> from scipy import optimize

    >>> def f(x):
    ...     return (x**3 - 1)  # only one real root at x = 1

    ``fprime`` is not provided, use the secant method:

    >>> root = optimize.newton(f, 1.5)
    >>> root
    1.0000000000000016
    >>> root = optimize.newton(f, 1.5, fprime2=lambda x: 6 * x)
    >>> root
    1.0000000000000016

    Only ``fprime`` is provided, use the Newton-Raphson method:

    >>> root = optimize.newton(f, 1.5, fprime=lambda x: 3 * x**2)
    >>> root
    1.0

    Both ``fprime2`` and ``fprime`` are provided, use Halley's method:

    >>> root = optimize.newton(f, 1.5, fprime=lambda x: 3 * x**2,
    ...                        fprime2=lambda x: 6 * x)
    >>> root
    1.0

    When we want to find roots for a set of related starting values and/or
    function parameters, we can provide both of those as an array of inputs:

    >>> f = lambda x, a: x**3 - a
    >>> fder = lambda x, a: 3 * x**2
    >>> rng = np.random.default_rng()
    >>> x = rng.standard_normal(100)
    >>> a = np.arange(-50, 50)
    >>> vec_res = optimize.newton(f, x, fprime=fder, args=(a, ), maxiter=200)

    The above is the equivalent of solving for each value in ``(x, a)``
    separately in a for-loop, just faster:

    >>> loop_res = [optimize.newton(f, x0, fprime=fder, args=(a0,),
    ...                             maxiter=200)
    ...             for x0, a0 in zip(x, a)]
    >>> np.allclose(vec_res, loop_res)
    True

    Plot the results found for all values of ``a``:

    >>> analytical_result = np.sign(a) * np.abs(a)**(1/3)
    >>> fig, ax = plt.subplots()
    >>> ax.plot(a, analytical_result, 'o')
    >>> ax.plot(a, vec_res, '.')
    >>> ax.set_xlabel('$a$')
    >>> ax.set_ylabel('$x$ where $f(x, a)=0$')
    >>> plt.show()

    """
    if tol <= 0:
        raise ValueError("tol too small (%g <= 0)" % tol)
    maxiter = operator.index(maxiter)
    if maxiter < 1:
        raise ValueError("maxiter must be greater than 0")
    if np.size(x0) > 1:
        return _array_newton(func, x0, fprime, args, tol, maxiter, fprime2,
                             full_output)

    # Convert to float (don't use float(x0); this works also for complex x0)
    x0 = np.asarray(x0)[()]
    p0 = x0
    funcalls = 0
    if fprime is not None:
        # Newton-Raphson method
        for itr in range(maxiter):
            # first evaluate fval
            fval = func(p0, *args)
            funcalls += 1
            # If fval is 0, a root has been found, then terminate
            if fval == 0:
                return _results_select(
                    full_output, (p0, funcalls, itr, _ECONVERGED))
            fder = fprime(p0, *args)
            funcalls += 1
            if fder == 0:
                msg = "Derivative was zero."
                if disp:
                    msg += (
                        " Failed to converge after %d iterations, value is %s."
                        % (itr + 1, p0))
                    raise RuntimeError(msg)
                warnings.warn(msg, RuntimeWarning)
                return _results_select(
                    full_output, (p0, funcalls, itr + 1, _ECONVERR))
            newton_step = fval / fder
            if fprime2:
                fder2 = fprime2(p0, *args)
                funcalls += 1
                # Halley's method:
                #   newton_step /= (1.0 - 0.5 * newton_step * fder2 / fder)
                # Only do it if denominator stays close enough to 1
                # Rationale: If 1-adj < 0, then Halley sends x in the
                # opposite direction to Newton. Doesn't happen if x is close
                # enough to root.
                adj = newton_step * fder2 / fder / 2
                if np.abs(adj) < 1:
                    newton_step /= 1.0 - adj
            p = p0 - newton_step
            if np.isclose(p, p0, rtol=rtol, atol=tol):
                return _results_select(
                    full_output, (p, funcalls, itr + 1, _ECONVERGED))
            p0 = p
    else:
        # Secant method
        if x1 is not None:
            if x1 == x0:
                raise ValueError("x1 and x0 must be different")
            p1 = x1
        else:
            eps = 1e-4
            p1 = x0 * (1 + eps)
            p1 += (eps if p1 >= 0 else -eps)
        q0 = func(p0, *args)
        funcalls += 1
        q1 = func(p1, *args)
        funcalls += 1
        if abs(q1) < abs(q0):
            p0, p1, q0, q1 = p1, p0, q1, q0
        for itr in range(maxiter):
            if q1 == q0:
                if p1 != p0:
                    msg = "Tolerance of %s reached." % (p1 - p0)
                    if disp:
                        msg += (
                            " Failed to converge after %d iterations, value is %s."
                            % (itr + 1, p1))
                        raise RuntimeError(msg)
                    warnings.warn(msg, RuntimeWarning)
                p = (p1 + p0) / 2.0
                return _results_select(
                    full_output, (p, funcalls, itr + 1, _ECONVERR))
            else:
                if abs(q1) > abs(q0):
                    p = (-q0 / q1 * p1 + p0) / (1 - q0 / q1)
                else:
                    p = (-q1 / q0 * p0 + p1) / (1 - q1 / q0)
            if np.isclose(p, p1, rtol=rtol, atol=tol):
                return _results_select(
                    full_output, (p, funcalls, itr + 1, _ECONVERGED))
            p0, q0 = p1, q1
            p1 = p
            q1 = func(p1, *args)
            funcalls += 1

    if disp:
        msg = ("Failed to converge after %d iterations, value is %s."
               % (itr + 1, p))
        raise RuntimeError(msg)

    return _results_select(full_output, (p, funcalls, itr + 1, _ECONVERR))


def _array_newton(func, x0, fprime, args, tol, maxiter, fprime2, full_output):
    """
    A vectorized version of Newton, Halley, and secant methods for arrays.

    Do not use this method directly. This method is called from `newton`
    when ``np.size(x0) > 1`` is ``True``. For docstring, see `newton`.
    """
    # Explicitly copy `x0` as `p` will be modified inplace, but the
    # user's array should not be altered.
    p = np.array(x0, copy=True)

    failures = np.ones_like(p, dtype=bool)
    nz_der = np.ones_like(failures)
    if fprime is not None:
        # Newton-Raphson method
        for iteration in range(maxiter):
            # first evaluate fval
            fval = np.asarray(func(p, *args))
            # If all fval are 0, all roots have been found, then terminate
            if not fval.any():
                failures = fval.astype(bool)
                break
            fder = np.asarray(fprime(p, *args))
            nz_der = (fder != 0)
            # stop iterating if all derivatives are zero
            if not nz_der.any():
                break
            # Newton step
            dp = fval[nz_der] / fder[nz_der]
            if fprime2 is not None:
                fder2 = np.asarray(fprime2(p, *args))
                dp = dp / (1.0 - 0.5 * dp * fder2[nz_der] / fder[nz_der])
            # only update nonzero derivatives
            p = np.asarray(p, dtype=np.result_type(p, dp, np.float64))
            p[nz_der] -= dp
            failures[nz_der] = np.abs(dp) >= tol  # items not yet converged
            # stop iterating if there aren't any failures, not incl zero der
            if not failures[nz_der].any():
                break
    else:
        # Secant method
        dx = np.finfo(float).eps**0.33
        p1 = p * (1 + dx) + np.where(p >= 0, dx, -dx)
        q0 = np.asarray(func(p, *args))
        q1 = np.asarray(func(p1, *args))
        active = np.ones_like(p, dtype=bool)
        for iteration in range(maxiter):
            nz_der = (q1 != q0)
            # stop iterating if all derivatives are zero
            if not nz_der.any():
                p = (p1 + p) / 2.0
                break
            # Secant Step
            dp = (q1 * (p1 - p))[nz_der] / (q1 - q0)[nz_der]
            # only update nonzero derivatives
            p = np.asarray(p, dtype=np.result_type(p, p1, dp, np.float64))
            p[nz_der] = p1[nz_der] - dp
            active_zero_der = ~nz_der & active
            p[active_zero_der] = (p1 + p)[active_zero_der] / 2.0
            active &= nz_der  # don't assign zero derivatives again
            failures[nz_der] = np.abs(dp) >= tol  # not yet converged
            # stop iterating if there aren't any failures, not incl zero der
            if not failures[nz_der].any():
                break
            p1, p = p, p1
            q0 = q1
            q1 = np.asarray(func(p1, *args))

    zero_der = ~nz_der & failures  # don't include converged with zero-ders
    if zero_der.any():
        # Secant warnings
        if fprime is None:
            nonzero_dp = (p1 != p)
            # non-zero dp, but infinite newton step
            zero_der_nz_dp = (zero_der & nonzero_dp)
            if zero_der_nz_dp.any():
                rms = np.sqrt(
                    sum((p1[zero_der_nz_dp] - p[zero_der_nz_dp]) ** 2)
                )
                warnings.warn(
                    f'RMS of {rms:g} reached', RuntimeWarning)
        # Newton or Halley warnings
        else:
            all_or_some = 'all' if zero_der.all() else 'some'
            msg = f'{all_or_some:s} derivatives were zero'
            warnings.warn(msg, RuntimeWarning)
    elif failures.any():
        all_or_some = 'all' if failures.all() else 'some'
        msg = '{:s} failed to converge after {:d} iterations'.format(
            all_or_some, maxiter
        )
        if failures.all():
            raise RuntimeError(msg)
        warnings.warn(msg, RuntimeWarning)

    if full_output:
        result = namedtuple('result', ('root', 'converged', 'zero_der'))
        p = result(p, ~failures, zero_der)

    return p


def bisect(f, a, b, args=(),
           xtol=_xtol, rtol=_rtol, maxiter=_iter,
           full_output=False, disp=True):
    """
    Find root of a function within an interval using bisection.

    Basic bisection routine to find a root of the function `f` between the
    arguments `a` and `b`. `f(a)` and `f(b)` cannot have the same signs.
    Slow but sure.

    Parameters
    ----------
    f : function
        Python function returning a number.  `f` must be continuous, and
        f(a) and f(b) must have opposite signs.
    a : scalar
        One end of the bracketing interval [a,b].
    b : scalar
        The other end of the bracketing interval [a,b].
    xtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter must be positive.
    rtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter cannot be smaller than its default value of
        ``4*np.finfo(float).eps``.
    maxiter : int, optional
        If convergence is not achieved in `maxiter` iterations, an error is
        raised. Must be >= 0.
    args : tuple, optional
        Containing extra arguments for the function `f`.
        `f` is called by ``apply(f, (x)+args)``.
    full_output : bool, optional
        If `full_output` is False, the root is returned. If `full_output` is
        True, the return value is ``(x, r)``, where x is the root, and r is
        a `RootResults` object.
    disp : bool, optional
        If True, raise RuntimeError if the algorithm didn't converge.
        Otherwise, the convergence status is recorded in a `RootResults`
        return object.

    Returns
    -------
    root : float
        Root of `f` between `a` and `b`.
    r : `RootResults` (present if ``full_output = True``)
        Object containing information about the convergence. In particular,
        ``r.converged`` is True if the routine converged.

    Examples
    --------

    >>> def f(x):
    ...     return (x**2 - 1)

    >>> from scipy import optimize

    >>> root = optimize.bisect(f, 0, 2)
    >>> root
    1.0

    >>> root = optimize.bisect(f, -2, 0)
    >>> root
    -1.0

    See Also
    --------
    brentq, brenth, bisect, newton
    fixed_point : scalar fixed-point finder
    fsolve : n-dimensional root-finding

    """
    if not isinstance(args, tuple):
        args = (args,)
    maxiter = operator.index(maxiter)
    if xtol <= 0:
        raise ValueError("xtol too small (%g <= 0)" % xtol)
    if rtol < _rtol:
        raise ValueError(f"rtol too small ({rtol:g} < {_rtol:g})")
    f = _wrap_nan_raise(f)
    r = _zeros._bisect(f, a, b, xtol, rtol, maxiter, args, full_output, disp)
    return results_c(full_output, r)


def ridder(f, a, b, args=(),
           xtol=_xtol, rtol=_rtol, maxiter=_iter,
           full_output=False, disp=True):
    """
    Find a root of a function in an interval using Ridder's method.

    Parameters
    ----------
    f : function
        Python function returning a number. f must be continuous, and f(a) and
        f(b) must have opposite signs.
    a : scalar
        One end of the bracketing interval [a,b].
    b : scalar
        The other end of the bracketing interval [a,b].
    xtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter must be positive.
    rtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter cannot be smaller than its default value of
        ``4*np.finfo(float).eps``.
    maxiter : int, optional
        If convergence is not achieved in `maxiter` iterations, an error is
        raised. Must be >= 0.
    args : tuple, optional
        Containing extra arguments for the function `f`.
        `f` is called by ``apply(f, (x)+args)``.
    full_output : bool, optional
        If `full_output` is False, the root is returned. If `full_output` is
        True, the return value is ``(x, r)``, where `x` is the root, and `r` is
        a `RootResults` object.
    disp : bool, optional
        If True, raise RuntimeError if the algorithm didn't converge.
        Otherwise, the convergence status is recorded in any `RootResults`
        return object.

    Returns
    -------
    root : float
        Root of `f` between `a` and `b`.
    r : `RootResults` (present if ``full_output = True``)
        Object containing information about the convergence.
        In particular, ``r.converged`` is True if the routine converged.

    See Also
    --------
    brentq, brenth, bisect, newton : 1-D root-finding
    fixed_point : scalar fixed-point finder

    Notes
    -----
    Uses [Ridders1979]_ method to find a root of the function `f` between the
    arguments `a` and `b`. Ridders' method is faster than bisection, but not
    generally as fast as the Brent routines. [Ridders1979]_ provides the
    classic description and source of the algorithm. A description can also be
    found in any recent edition of Numerical Recipes.

    The routine used here diverges slightly from standard presentations in
    order to be a bit more careful of tolerance.

    References
    ----------
    .. [Ridders1979]
       Ridders, C. F. J. "A New Algorithm for Computing a
       Single Root of a Real Continuous Function."
       IEEE Trans. Circuits Systems 26, 979-980, 1979.

    Examples
    --------

    >>> def f(x):
    ...     return (x**2 - 1)

    >>> from scipy import optimize

    >>> root = optimize.ridder(f, 0, 2)
    >>> root
    1.0

    >>> root = optimize.ridder(f, -2, 0)
    >>> root
    -1.0
    """
    if not isinstance(args, tuple):
        args = (args,)
    maxiter = operator.index(maxiter)
    if xtol <= 0:
        raise ValueError("xtol too small (%g <= 0)" % xtol)
    if rtol < _rtol:
        raise ValueError(f"rtol too small ({rtol:g} < {_rtol:g})")
    f = _wrap_nan_raise(f)
    r = _zeros._ridder(f, a, b, xtol, rtol, maxiter, args, full_output, disp)
    return results_c(full_output, r)


def brentq(f, a, b, args=(),
           xtol=_xtol, rtol=_rtol, maxiter=_iter,
           full_output=False, disp=True):
    """
    Find a root of a function in a bracketing interval using Brent's method.

    Uses the classic Brent's method to find a root of the function `f` on
    the sign changing interval [a , b]. Generally considered the best of the
    rootfinding routines here. It is a safe version of the secant method that
    uses inverse quadratic extrapolation. Brent's method combines root
    bracketing, interval bisection, and inverse quadratic interpolation. It is
    sometimes known as the van Wijngaarden-Dekker-Brent method. Brent (1973)
    claims convergence is guaranteed for functions computable within [a,b].

    [Brent1973]_ provides the classic description of the algorithm. Another
    description can be found in a recent edition of Numerical Recipes, including
    [PressEtal1992]_. A third description is at
    http://mathworld.wolfram.com/BrentsMethod.html. It should be easy to
    understand the algorithm just by reading our code. Our code diverges a bit
    from standard presentations: we choose a different formula for the
    extrapolation step.

    Parameters
    ----------
    f : function
        Python function returning a number. The function :math:`f`
        must be continuous, and :math:`f(a)` and :math:`f(b)` must
        have opposite signs.
    a : scalar
        One end of the bracketing interval :math:`[a, b]`.
    b : scalar
        The other end of the bracketing interval :math:`[a, b]`.
    xtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter must be positive. For nice functions, Brent's
        method will often satisfy the above condition with ``xtol/2``
        and ``rtol/2``. [Brent1973]_
    rtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter cannot be smaller than its default value of
        ``4*np.finfo(float).eps``. For nice functions, Brent's
        method will often satisfy the above condition with ``xtol/2``
        and ``rtol/2``. [Brent1973]_
    maxiter : int, optional
        If convergence is not achieved in `maxiter` iterations, an error is
        raised. Must be >= 0.
    args : tuple, optional
        Containing extra arguments for the function `f`.
        `f` is called by ``apply(f, (x)+args)``.
    full_output : bool, optional
        If `full_output` is False, the root is returned. If `full_output` is
        True, the return value is ``(x, r)``, where `x` is the root, and `r` is
        a `RootResults` object.
    disp : bool, optional
        If True, raise RuntimeError if the algorithm didn't converge.
        Otherwise, the convergence status is recorded in any `RootResults`
        return object.

    Returns
    -------
    root : float
        Root of `f` between `a` and `b`.
    r : `RootResults` (present if ``full_output = True``)
        Object containing information about the convergence. In particular,
        ``r.converged`` is True if the routine converged.

    Notes
    -----
    `f` must be continuous.  f(a) and f(b) must have opposite signs.

    Related functions fall into several classes:

    multivariate local optimizers
      `fmin`, `fmin_powell`, `fmin_cg`, `fmin_bfgs`, `fmin_ncg`
    nonlinear least squares minimizer
      `leastsq`
    constrained multivariate optimizers
      `fmin_l_bfgs_b`, `fmin_tnc`, `fmin_cobyla`
    global optimizers
      `basinhopping`, `brute`, `differential_evolution`
    local scalar minimizers
      `fminbound`, `brent`, `golden`, `bracket`
    N-D root-finding
      `fsolve`
    1-D root-finding
      `brenth`, `ridder`, `bisect`, `newton`
    scalar fixed-point finder
      `fixed_point`

    References
    ----------
    .. [Brent1973]
       Brent, R. P.,
       *Algorithms for Minimization Without Derivatives*.
       Englewood Cliffs, NJ: Prentice-Hall, 1973. Ch. 3-4.

    .. [PressEtal1992]
       Press, W. H.; Flannery, B. P.; Teukolsky, S. A.; and Vetterling, W. T.
       *Numerical Recipes in FORTRAN: The Art of Scientific Computing*, 2nd ed.
       Cambridge, England: Cambridge University Press, pp. 352-355, 1992.
       Section 9.3:  "Van Wijngaarden-Dekker-Brent Method."

    Examples
    --------
    >>> def f(x):
    ...     return (x**2 - 1)

    >>> from scipy import optimize

    >>> root = optimize.brentq(f, -2, 0)
    >>> root
    -1.0

    >>> root = optimize.brentq(f, 0, 2)
    >>> root
    1.0
    """
    if not isinstance(args, tuple):
        args = (args,)
    maxiter = operator.index(maxiter)
    if xtol <= 0:
        raise ValueError("xtol too small (%g <= 0)" % xtol)
    if rtol < _rtol:
        raise ValueError(f"rtol too small ({rtol:g} < {_rtol:g})")
    f = _wrap_nan_raise(f)
    r = _zeros._brentq(f, a, b, xtol, rtol, maxiter, args, full_output, disp)
    return results_c(full_output, r)


def brenth(f, a, b, args=(),
           xtol=_xtol, rtol=_rtol, maxiter=_iter,
           full_output=False, disp=True):
    """Find a root of a function in a bracketing interval using Brent's
    method with hyperbolic extrapolation.

    A variation on the classic Brent routine to find a root of the function f
    between the arguments a and b that uses hyperbolic extrapolation instead of
    inverse quadratic extrapolation. Bus & Dekker (1975) guarantee convergence
    for this method, claiming that the upper bound of function evaluations here
    is 4 or 5 times lesser than that for bisection.
    f(a) and f(b) cannot have the same signs. Generally, on a par with the
    brent routine, but not as heavily tested. It is a safe version of the
    secant method that uses hyperbolic extrapolation.
    The version here is by Chuck Harris, and implements Algorithm M of
    [BusAndDekker1975]_, where further details (convergence properties,
    additional remarks and such) can be found

    Parameters
    ----------
    f : function
        Python function returning a number. f must be continuous, and f(a) and
        f(b) must have opposite signs.
    a : scalar
        One end of the bracketing interval [a,b].
    b : scalar
        The other end of the bracketing interval [a,b].
    xtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter must be positive. As with `brentq`, for nice
        functions the method will often satisfy the above condition
        with ``xtol/2`` and ``rtol/2``.
    rtol : number, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter cannot be smaller than its default value of
        ``4*np.finfo(float).eps``. As with `brentq`, for nice functions
        the method will often satisfy the above condition with
        ``xtol/2`` and ``rtol/2``.
    maxiter : int, optional
        If convergence is not achieved in `maxiter` iterations, an error is
        raised. Must be >= 0.
    args : tuple, optional
        Containing extra arguments for the function `f`.
        `f` is called by ``apply(f, (x)+args)``.
    full_output : bool, optional
        If `full_output` is False, the root is returned. If `full_output` is
        True, the return value is ``(x, r)``, where `x` is the root, and `r` is
        a `RootResults` object.
    disp : bool, optional
        If True, raise RuntimeError if the algorithm didn't converge.
        Otherwise, the convergence status is recorded in any `RootResults`
        return object.

    Returns
    -------
    root : float
        Root of `f` between `a` and `b`.
    r : `RootResults` (present if ``full_output = True``)
        Object containing information about the convergence. In particular,
        ``r.converged`` is True if the routine converged.

    See Also
    --------
    fmin, fmin_powell, fmin_cg, fmin_bfgs, fmin_ncg : multivariate local optimizers
    leastsq : nonlinear least squares minimizer
    fmin_l_bfgs_b, fmin_tnc, fmin_cobyla : constrained multivariate optimizers
    basinhopping, differential_evolution, brute : global optimizers
    fminbound, brent, golden, bracket : local scalar minimizers
    fsolve : N-D root-finding
    brentq, brenth, ridder, bisect, newton : 1-D root-finding
    fixed_point : scalar fixed-point finder

    References
    ----------
    .. [BusAndDekker1975]
       Bus, J. C. P., Dekker, T. J.,
       "Two Efficient Algorithms with Guaranteed Convergence for Finding a Zero
       of a Function", ACM Transactions on Mathematical Software, Vol. 1, Issue
       4, Dec. 1975, pp. 330-345. Section 3: "Algorithm M".
       :doi:`10.1145/355656.355659`

    Examples
    --------
    >>> def f(x):
    ...     return (x**2 - 1)

    >>> from scipy import optimize

    >>> root = optimize.brenth(f, -2, 0)
    >>> root
    -1.0

    >>> root = optimize.brenth(f, 0, 2)
    >>> root
    1.0

    """
    if not isinstance(args, tuple):
        args = (args,)
    maxiter = operator.index(maxiter)
    if xtol <= 0:
        raise ValueError("xtol too small (%g <= 0)" % xtol)
    if rtol < _rtol:
        raise ValueError(f"rtol too small ({rtol:g} < {_rtol:g})")
    f = _wrap_nan_raise(f)
    r = _zeros._brenth(f, a, b, xtol, rtol, maxiter, args, full_output, disp)
    return results_c(full_output, r)


################################
# TOMS "Algorithm 748: Enclosing Zeros of Continuous Functions", by
#  Alefeld, G. E. and Potra, F. A. and Shi, Yixun,
#  See [1]


def _notclose(fs, rtol=_rtol, atol=_xtol):
    # Ensure not None, not 0, all finite, and not very close to each other
    notclosefvals = (
            all(fs) and all(np.isfinite(fs)) and
            not any(any(np.isclose(_f, fs[i + 1:], rtol=rtol, atol=atol))
                    for i, _f in enumerate(fs[:-1])))
    return notclosefvals


def _secant(xvals, fvals):
    """Perform a secant step, taking a little care"""
    # Secant has many "mathematically" equivalent formulations
    # x2 = x0 - (x1 - x0)/(f1 - f0) * f0
    #    = x1 - (x1 - x0)/(f1 - f0) * f1
    #    = (-x1 * f0 + x0 * f1) / (f1 - f0)
    #    = (-f0 / f1 * x1 + x0) / (1 - f0 / f1)
    #    = (-f1 / f0 * x0 + x1) / (1 - f1 / f0)
    x0, x1 = xvals[:2]
    f0, f1 = fvals[:2]
    if f0 == f1:
        return np.nan
    if np.abs(f1) > np.abs(f0):
        x2 = (-f0 / f1 * x1 + x0) / (1 - f0 / f1)
    else:
        x2 = (-f1 / f0 * x0 + x1) / (1 - f1 / f0)
    return x2


def _update_bracket(ab, fab, c, fc):
    """Update a bracket given (c, fc), return the discarded endpoints."""
    fa, fb = fab
    idx = (0 if np.sign(fa) * np.sign(fc) > 0 else 1)
    rx, rfx = ab[idx], fab[idx]
    fab[idx] = fc
    ab[idx] = c
    return rx, rfx


def _compute_divided_differences(xvals, fvals, N=None, full=True,
                                 forward=True):
    """Return a matrix of divided differences for the xvals, fvals pairs

    DD[i, j] = f[x_{i-j}, ..., x_i] for 0 <= j <= i

    If full is False, just return the main diagonal(or last row):
      f[a], f[a, b] and f[a, b, c].
    If forward is False, return f[c], f[b, c], f[a, b, c]."""
    if full:
        if forward:
            xvals = np.asarray(xvals)
        else:
            xvals = np.array(xvals)[::-1]
        M = len(xvals)
        N = M if N is None else min(N, M)
        DD = np.zeros([M, N])
        DD[:, 0] = fvals[:]
        for i in range(1, N):
            DD[i:, i] = (np.diff(DD[i - 1:, i - 1]) /
                         (xvals[i:] - xvals[:M - i]))
        return DD

    xvals = np.asarray(xvals)
    dd = np.array(fvals)
    row = np.array(fvals)
    idx2Use = (0 if forward else -1)
    dd[0] = fvals[idx2Use]
    for i in range(1, len(xvals)):
        denom = xvals[i:i + len(row) - 1] - xvals[:len(row) - 1]
        row = np.diff(row)[:] / denom
        dd[i] = row[idx2Use]
    return dd


def _interpolated_poly(xvals, fvals, x):
    """Compute p(x) for the polynomial passing through the specified locations.

    Use Neville's algorithm to compute p(x) where p is the minimal degree
    polynomial passing through the points xvals, fvals"""
    xvals = np.asarray(xvals)
    N = len(xvals)
    Q = np.zeros([N, N])
    D = np.zeros([N, N])
    Q[:, 0] = fvals[:]
    D[:, 0] = fvals[:]
    for k in range(1, N):
        alpha = D[k:, k - 1] - Q[k - 1:N - 1, k - 1]
        diffik = xvals[0:N - k] - xvals[k:N]
        Q[k:, k] = (xvals[k:] - x) / diffik * alpha
        D[k:, k] = (xvals[:N - k] - x) / diffik * alpha
    # Expect Q[-1, 1:] to be small relative to Q[-1, 0] as x approaches a root
    return np.sum(Q[-1, 1:]) + Q[-1, 0]


def _inverse_poly_zero(a, b, c, d, fa, fb, fc, fd):
    """Inverse cubic interpolation f-values -> x-values

    Given four points (fa, a), (fb, b), (fc, c), (fd, d) with
    fa, fb, fc, fd all distinct, find poly IP(y) through the 4 points
    and compute x=IP(0).
    """
    return _interpolated_poly([fa, fb, fc, fd], [a, b, c, d], 0)


def _newton_quadratic(ab, fab, d, fd, k):
    """Apply Newton-Raphson like steps, using divided differences to approximate f'

    ab is a real interval [a, b] containing a root,
    fab holds the real values of f(a), f(b)
    d is a real number outside [ab, b]
    k is the number of steps to apply
    """
    a, b = ab
    fa, fb = fab
    _, B, A = _compute_divided_differences([a, b, d], [fa, fb, fd],
                                           forward=True, full=False)

    # _P  is the quadratic polynomial through the 3 points
    def _P(x):
        # Horner evaluation of fa + B * (x - a) + A * (x - a) * (x - b)
        return (A * (x - b) + B) * (x - a) + fa

    if A == 0:
        r = a - fa / B
    else:
        r = (a if np.sign(A) * np.sign(fa) > 0 else b)
        # Apply k Newton-Raphson steps to _P(x), starting from x=r
        for i in range(k):
            r1 = r - _P(r) / (B + A * (2 * r - a - b))
            if not (ab[0] < r1 < ab[1]):
                if (ab[0] < r < ab[1]):
                    return r
                r = sum(ab) / 2.0
                break
            r = r1

    return r


class TOMS748Solver:
    """Solve f(x, *args) == 0 using Algorithm748 of Alefeld, Potro & Shi.
    """
    _MU = 0.5
    _K_MIN = 1
    _K_MAX = 100  # A very high value for real usage. Expect 1, 2, maybe 3.

    def __init__(self):
        self.f = None
        self.args = None
        self.function_calls = 0
        self.iterations = 0
        self.k = 2
        # ab=[a,b] is a global interval containing a root
        self.ab = [np.nan, np.nan]
        # fab is function values at a, b
        self.fab = [np.nan, np.nan]
        self.d = None
        self.fd = None
        self.e = None
        self.fe = None
        self.disp = False
        self.xtol = _xtol
        self.rtol = _rtol
        self.maxiter = _iter

    def configure(self, xtol, rtol, maxiter, disp, k):
        self.disp = disp
        self.xtol = xtol
        self.rtol = rtol
        self.maxiter = maxiter
        # Silently replace a low value of k with 1
        self.k = max(k, self._K_MIN)
        # Noisily replace a high value of k with self._K_MAX
        if self.k > self._K_MAX:
            msg = "toms748: Overriding k: ->%d" % self._K_MAX
            warnings.warn(msg, RuntimeWarning)
            self.k = self._K_MAX

    def _callf(self, x, error=True):
        """Call the user-supplied function, update book-keeping"""
        fx = self.f(x, *self.args)
        self.function_calls += 1
        if not np.isfinite(fx) and error:
            raise ValueError(f"Invalid function value: f({x:f}) -> {fx} ")
        return fx

    def get_result(self, x, flag=_ECONVERGED):
        r"""Package the result and statistics into a tuple."""
        return (x, self.function_calls, self.iterations, flag)

    def _update_bracket(self, c, fc):
        return _update_bracket(self.ab, self.fab, c, fc)

    def start(self, f, a, b, args=()):
        r"""Prepare for the iterations."""
        self.function_calls = 0
        self.iterations = 0

        self.f = f
        self.args = args
        self.ab[:] = [a, b]
        if not np.isfinite(a) or np.imag(a) != 0:
            raise ValueError("Invalid x value: %s " % (a))
        if not np.isfinite(b) or np.imag(b) != 0:
            raise ValueError("Invalid x value: %s " % (b))

        fa = self._callf(a)
        if not np.isfinite(fa) or np.imag(fa) != 0:
            raise ValueError(f"Invalid function value: f({a:f}) -> {fa} ")
        if fa == 0:
            return _ECONVERGED, a
        fb = self._callf(b)
        if not np.isfinite(fb) or np.imag(fb) != 0:
            raise ValueError(f"Invalid function value: f({b:f}) -> {fb} ")
        if fb == 0:
            return _ECONVERGED, b

        if np.sign(fb) * np.sign(fa) > 0:
            raise ValueError("f(a) and f(b) must have different signs, but "
                             "f({:e})={:e}, f({:e})={:e} ".format(a, fa, b, fb))
        self.fab[:] = [fa, fb]

        return _EINPROGRESS, sum(self.ab) / 2.0

    def get_status(self):
        """Determine the current status."""
        a, b = self.ab[:2]
        if np.isclose(a, b, rtol=self.rtol, atol=self.xtol):
            return _ECONVERGED, sum(self.ab) / 2.0
        if self.iterations >= self.maxiter:
            return _ECONVERR, sum(self.ab) / 2.0
        return _EINPROGRESS, sum(self.ab) / 2.0

    def iterate(self):
        """Perform one step in the algorithm.

        Implements Algorithm 4.1(k=1) or 4.2(k=2) in [APS1995]
        """
        self.iterations += 1
        eps = np.finfo(float).eps
        d, fd, e, fe = self.d, self.fd, self.e, self.fe
        ab_width = self.ab[1] - self.ab[0]  # Need the start width below
        c = None

        for nsteps in range(2, self.k+2):
            # If the f-values are sufficiently separated, perform an inverse
            # polynomial interpolation step. Otherwise, nsteps repeats of
            # an approximate Newton-Raphson step.
            if _notclose(self.fab + [fd, fe], rtol=0, atol=32*eps):
                c0 = _inverse_poly_zero(self.ab[0], self.ab[1], d, e,
                                        self.fab[0], self.fab[1], fd, fe)
                if self.ab[0] < c0 < self.ab[1]:
                    c = c0
            if c is None:
                c = _newton_quadratic(self.ab, self.fab, d, fd, nsteps)

            fc = self._callf(c)
            if fc == 0:
                return _ECONVERGED, c

            # re-bracket
            e, fe = d, fd
            d, fd = self._update_bracket(c, fc)

        # u is the endpoint with the smallest f-value
        uix = (0 if np.abs(self.fab[0]) < np.abs(self.fab[1]) else 1)
        u, fu = self.ab[uix], self.fab[uix]

        _, A = _compute_divided_differences(self.ab, self.fab,
                                            forward=(uix == 0), full=False)
        c = u - 2 * fu / A
        if np.abs(c - u) > 0.5 * (self.ab[1] - self.ab[0]):
            c = sum(self.ab) / 2.0
        else:
            if np.isclose(c, u, rtol=eps, atol=0):
                # c didn't change (much).
                # Either because the f-values at the endpoints have vastly
                # differing magnitudes, or because the root is very close to
                # that endpoint
                frs = np.frexp(self.fab)[1]
                if frs[uix] < frs[1 - uix] - 50:  # Differ by more than 2**50
                    c = (31 * self.ab[uix] + self.ab[1 - uix]) / 32
                else:
                    # Make a bigger adjustment, about the
                    # size of the requested tolerance.
                    mm = (1 if uix == 0 else -1)
                    adj = mm * np.abs(c) * self.rtol + mm * self.xtol
                    c = u + adj
                if not self.ab[0] < c < self.ab[1]:
                    c = sum(self.ab) / 2.0

        fc = self._callf(c)
        if fc == 0:
            return _ECONVERGED, c

        e, fe = d, fd
        d, fd = self._update_bracket(c, fc)

        # If the width of the new interval did not decrease enough, bisect
        if self.ab[1] - self.ab[0] > self._MU * ab_width:
            e, fe = d, fd
            z = sum(self.ab) / 2.0
            fz = self._callf(z)
            if fz == 0:
                return _ECONVERGED, z
            d, fd = self._update_bracket(z, fz)

        # Record d and e for next iteration
        self.d, self.fd = d, fd
        self.e, self.fe = e, fe

        status, xn = self.get_status()
        return status, xn

    def solve(self, f, a, b, args=(),
              xtol=_xtol, rtol=_rtol, k=2, maxiter=_iter, disp=True):
        r"""Solve f(x) = 0 given an interval containing a root."""
        self.configure(xtol=xtol, rtol=rtol, maxiter=maxiter, disp=disp, k=k)
        status, xn = self.start(f, a, b, args)
        if status == _ECONVERGED:
            return self.get_result(xn)

        # The first step only has two x-values.
        c = _secant(self.ab, self.fab)
        if not self.ab[0] < c < self.ab[1]:
            c = sum(self.ab) / 2.0
        fc = self._callf(c)
        if fc == 0:
            return self.get_result(c)

        self.d, self.fd = self._update_bracket(c, fc)
        self.e, self.fe = None, None
        self.iterations += 1

        while True:
            status, xn = self.iterate()
            if status == _ECONVERGED:
                return self.get_result(xn)
            if status == _ECONVERR:
                fmt = "Failed to converge after %d iterations, bracket is %s"
                if disp:
                    msg = fmt % (self.iterations + 1, self.ab)
                    raise RuntimeError(msg)
                return self.get_result(xn, _ECONVERR)


def toms748(f, a, b, args=(), k=1,
            xtol=_xtol, rtol=_rtol, maxiter=_iter,
            full_output=False, disp=True):
    """
    Find a root using TOMS Algorithm 748 method.

    Implements the Algorithm 748 method of Alefeld, Potro and Shi to find a
    root of the function `f` on the interval `[a , b]`, where `f(a)` and
    `f(b)` must have opposite signs.

    It uses a mixture of inverse cubic interpolation and
    "Newton-quadratic" steps. [APS1995].

    Parameters
    ----------
    f : function
        Python function returning a scalar. The function :math:`f`
        must be continuous, and :math:`f(a)` and :math:`f(b)`
        have opposite signs.
    a : scalar,
        lower boundary of the search interval
    b : scalar,
        upper boundary of the search interval
    args : tuple, optional
        containing extra arguments for the function `f`.
        `f` is called by ``f(x, *args)``.
    k : int, optional
        The number of Newton quadratic steps to perform each
        iteration. ``k>=1``.
    xtol : scalar, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root. The
        parameter must be positive.
    rtol : scalar, optional
        The computed root ``x0`` will satisfy ``np.allclose(x, x0,
        atol=xtol, rtol=rtol)``, where ``x`` is the exact root.
    maxiter : int, optional
        If convergence is not achieved in `maxiter` iterations, an error is
        raised. Must be >= 0.
    full_output : bool, optional
        If `full_output` is False, the root is returned. If `full_output` is
        True, the return value is ``(x, r)``, where `x` is the root, and `r` is
        a `RootResults` object.
    disp : bool, optional
        If True, raise RuntimeError if the algorithm didn't converge.
        Otherwise, the convergence status is recorded in the `RootResults`
        return object.

    Returns
    -------
    root : float
        Approximate root of `f`
    r : `RootResults` (present if ``full_output = True``)
        Object containing information about the convergence. In particular,
        ``r.converged`` is True if the routine converged.

    See Also
    --------
    brentq, brenth, ridder, bisect, newton
    fsolve : find roots in N dimensions.

    Notes
    -----
    `f` must be continuous.
    Algorithm 748 with ``k=2`` is asymptotically the most efficient
    algorithm known for finding roots of a four times continuously
    differentiable function.
    In contrast with Brent's algorithm, which may only decrease the length of
    the enclosing bracket on the last step, Algorithm 748 decreases it each
    iteration with the same asymptotic efficiency as it finds the root.

    For easy statement of efficiency indices, assume that `f` has 4
    continuouous deriviatives.
    For ``k=1``, the convergence order is at least 2.7, and with about
    asymptotically 2 function evaluations per iteration, the efficiency
    index is approximately 1.65.
    For ``k=2``, the order is about 4.6 with asymptotically 3 function
    evaluations per iteration, and the efficiency index 1.66.
    For higher values of `k`, the efficiency index approaches
    the kth root of ``(3k-2)``, hence ``k=1`` or ``k=2`` are
    usually appropriate.

    References
    ----------
    .. [APS1995]
       Alefeld, G. E. and Potra, F. A. and Shi, Yixun,
       *Algorithm 748: Enclosing Zeros of Continuous Functions*,
       ACM Trans. Math. Softw. Volume 221(1995)
       doi = {10.1145/210089.210111}

    Examples
    --------
    >>> def f(x):
    ...     return (x**3 - 1)  # only one real root at x = 1

    >>> from scipy import optimize
    >>> root, results = optimize.toms748(f, 0, 2, full_output=True)
    >>> root
    1.0
    >>> results
          converged: True
               flag: converged
     function_calls: 11
         iterations: 5
               root: 1.0
    """
    if xtol <= 0:
        raise ValueError("xtol too small (%g <= 0)" % xtol)
    if rtol < _rtol / 4:
        raise ValueError(f"rtol too small ({rtol:g} < {_rtol/4:g})")
    maxiter = operator.index(maxiter)
    if maxiter < 1:
        raise ValueError("maxiter must be greater than 0")
    if not np.isfinite(a):
        raise ValueError("a is not finite %s" % a)
    if not np.isfinite(b):
        raise ValueError("b is not finite %s" % b)
    if a >= b:
        raise ValueError(f"a and b are not an interval [{a}, {b}]")
    if not k >= 1:
        raise ValueError("k too small (%s < 1)" % k)

    if not isinstance(args, tuple):
        args = (args,)
    f = _wrap_nan_raise(f)
    solver = TOMS748Solver()
    result = solver.solve(f, a, b, args=args, k=k, xtol=xtol, rtol=rtol,
                          maxiter=maxiter, disp=disp)
    x, function_calls, iterations, flag = result
    return _results_select(full_output, (x, function_calls, iterations, flag))


def _chandrupatla(func, a, b, *, args=(), xatol=_xtol, xrtol=_rtol,
                  fatol=None, frtol=0, maxiter=_iter, callback=None):
    """Find the root of an elementwise function using Chandrupatla's algorithm.

    For each element of the output of `func`, `chandrupatla` seeks the scalar
    root that makes the element 0. This function allows for `a`, `b`, and the
    output of `func` to be of any broadcastable shapes.

    Parameters
    ----------
    func : callable
        The function whose root is desired. The signature must be::

            func(x: ndarray, *args) -> ndarray

         where each element of ``x`` is a finite real and ``args`` is a tuple,
         which may contain an arbitrary number of components of any type(s).
         ``func`` must be an elementwise function: each element ``func(x)[i]``
         must equal ``func(x[i])`` for all indices ``i``. `_chandrupatla`
         seeks an array ``x`` such that ``func(x)`` is an array of zeros.
    a, b : array_like
        The lower and upper bounds of the root of the function. Must be
        broadcastable with one another.
    args : tuple, optional
        Additional positional arguments to be passed to `func`.
    xatol, xrtol, fatol, frtol : float, optional
        Absolute and relative tolerances on the root and function value.
        See Notes for details.
    maxiter : int, optional
        The maximum number of iterations of the algorithm to perform.
    callback : callable, optional
        An optional user-supplied function to be called before the first
        iteration and after each iteration.
        Called as ``callback(res)``, where ``res`` is an ``OptimizeResult``
        similar to that returned by `_chandrupatla` (but containing the current
        iterate's values of all variables). If `callback` raises a
        ``StopIteration``, the algorithm will terminate immediately and
        `_chandrupatla` will return a result.

    Returns
    -------
    res : OptimizeResult
        An instance of `scipy.optimize.OptimizeResult` with the following
        attributes. The descriptions are written as though the values will be
        scalars; however, if `func` returns an array, the outputs will be
        arrays of the same shape.

        x : float
            The root of the function, if the algorithm terminated successfully.
        nfev : int
            The number of times the function was called to find the root.
        nit : int
            The number of iterations of Chandrupatla's algorithm performed.
        status : int
            An integer representing the exit status of the algorithm.
            ``0`` : The algorithm converged to the specified tolerances.
            ``-1`` : The algorithm encountered an invalid bracket.
            ``-2`` : The maximum number of iterations was reached.
            ``-3`` : A non-finite value was encountered.
            ``-4`` : Iteration was terminated by `callback`.
            ``1`` : The algorithm is proceeding normally (in `callback` only).
        success : bool
            ``True`` when the algorithm terminated successfully (status ``0``).
        fun : float
            The value of `func` evaluated at `x`.
        xl, xr : float
            The lower and upper ends of the bracket.
        fl, fr : float
            The function value at the lower and upper ends of the bracket.

    Notes
    -----
    Implemented based on Chandrupatla's original paper [1]_.

    If ``xl`` and ``xr`` are the left and right ends of the bracket,
    ``xmin = xl if abs(func(xl)) <= abs(func(xr)) else xr``,
    and ``fmin0 = min(func(a), func(b))``, then the algorithm is considered to
    have converged when ``abs(xr - xl) < xatol + abs(xmin) * xrtol`` or
    ``fun(xmin) <= fatol + abs(fmin0) * frtol``. This is equivalent to the
    termination condition described in [1]_ with ``xrtol = 4e-10``,
    ``xatol = 1e-5``, and ``fatol = frtol = 0``. The default values are
    ``xatol = 2e-12``, ``xrtol = 4 * np.finfo(float).eps``, ``frtol = 0``,
    and ``fatol`` is the smallest normal number of the ``dtype`` returned
    by ``func``.

    References
    ----------

    .. [1] Chandrupatla, Tirupathi R.
        "A new hybrid quadratic/bisection algorithm for finding the zero of a
        nonlinear function without using derivatives".
        Advances in Engineering Software, 28(3), 145-149.
        https://doi.org/10.1016/s0965-9978(96)00051-8

    See Also
    --------
    brentq, brenth, ridder, bisect, newton

    Examples
    --------
    >>> from scipy import optimize
    >>> def f(x, c):
    ...     return x**3 - 2*x - c
    >>> c = 5
    >>> res = optimize._zeros_py._chandrupatla(f, 0, 3, args=(c,))
    >>> res.x
    2.0945514818937463

    >>> c = [3, 4, 5]
    >>> res = optimize._zeros_py._chandrupatla(f, 0, 3, args=(c,))
    >>> res.x
    array([1.8932892 , 2.        , 2.09455148])

    """
    res = _chandrupatla_iv(func, a, b, args, xatol, xrtol,
                           fatol, frtol, maxiter, callback)
    func, a, b, args, xatol, xrtol, fatol, frtol, maxiter, callback = res

    # Initialization
    xs, fs, shape, dtype = _chandrupatla_initialize(func, (a, b), args)
    x1, x2 = xs
    f1, f2 = fs
    status = np.full_like(x1, _EINPROGRESS, dtype=int)  # in progress
    success = status == _ECONVERGED
    active = np.arange(x1.size)  # indices of in-progress elements
    nit, nfev = 0, 2  # two function evaluations performed above
    cb_terminate = False
    fatol = np.finfo(dtype).tiny if fatol is None else fatol
    frtol = frtol * np.minimum(np.abs(f1), np.abs(f2))
    work = OptimizeResult(x1=x1, f1=f1, x2=x2, f2=f2, x3=None, f3=None,
                          xatol=xatol, xrtol=xrtol, fatol=fatol, frtol=frtol,
                          nit=nit, nfev=nfev, status=status, success=success)

    # Elements of `x1`, `f1`, etc., are stored in this `OptimizeResult`
    # once a termination condition is met, and then the arrays are condensed
    # to reduce unnecessary computation.
    res = OptimizeResult(x=x1.copy(), fun=f1.copy(), xl=x1.copy(),
                         fl=f1.copy(), xr=x2.copy(), fr=f2.copy(),
                         nit=np.full_like(status, nit)[()],
                         nfev=np.full_like(status, nfev)[()],
                         status=status.copy(), success=(status==0))

    work, active = _chandrupatla_check_termination(work, res, active)

    if callback is not None:
        temp = _chandrupatla_prepare_result(shape, res, active, work)
        if _call_callback_maybe_halt(callback, temp):
            cb_terminate = True

    t = 0.5
    while work.nit < maxiter and active.size and not cb_terminate:
        # [1] Figure 1 (first box)
        x = work.x1 + t * (work.x2 - work.x1)

        # For now, we assume that `func` requires arguments of the original
        # shapes. However, `x` is compressed (contains only active elements).
        # Therefore, we inflate `x` by creating a full-size array, copying the
        # elements of `x` into it, and making it the expected shape.
        # TODO: allow user to specify that `func` works with compressed input
        x_full = res.x.copy()
        x_full[active] = x
        x_full = x_full.reshape(shape)[()]
        f = func(x_full, *args)
        work.nfev += 1
        # Ensure that the outpuf of `func` is an array of the appropriate
        # dtype, ravel it (because we work with 1D arrays for simplicity), and
        # compress it to contain only active elements.
        f = np.asarray(f, dtype=dtype).ravel()[active]

        # [1] Figure 1 (first diamond and boxes)
        # Note: y/n are reversed in figure; compare to BASIC in appendix
        work.x3, work.f3 = work.x2.copy(), work.f2.copy()
        j = np.sign(f) == np.sign(work.f1)
        nj = ~j
        work.x3[j], work.f3[j] = work.x1[j], work.f1[j]
        work.x2[nj], work.f2[nj] = work.x1[nj], work.f1[nj]
        work.x1, work.f1 = x, f

        # [1] Figure 1 (second diamond)
        work.nit += 1
        work, active = _chandrupatla_check_termination(work, res, active)

        if callback is not None:
            temp = _chandrupatla_prepare_result(shape, res, active, work)
            if _call_callback_maybe_halt(callback, temp):
                cb_terminate = True
                break
        if active.size==0:
            break

        # [1] Figure 1 (third diamond and boxes / Equation 1)
        xi1 = (work.x1 - work.x2) / (work.x3 - work.x2)
        phi1 = (work.f1 - work.f2) / (work.f3 - work.f2)
        alpha = (work.x3 - work.x1) / (work.x2 - work.x1)
        j = ((1 - np.sqrt(1 - xi1)) < phi1) & (phi1 < np.sqrt(xi1))

        f1j, f2j, f3j, alphaj = work.f1[j], work.f2[j], work.f3[j], alpha[j]
        t = np.full_like(alpha, 0.5)
        t[j] = (f1j / (f1j - f2j) * f3j / (f3j - f2j)
                - alphaj * f1j / (f3j - f1j) * f2j / (f2j - f3j))

        # [1] Figure 1 (last box; see also BASIC in appendix with comment
        # "Adjust T Away from the Interval Boundary")
        tl = 0.5 * work.tol / work.dx
        t = np.clip(t, tl, 1-tl)

    res.status[active] = _ECALLBACK if cb_terminate else _ECONVERR
    return _chandrupatla_prepare_result(shape, res, active, work)


def _chandrupatla_iv(func, a, b, args, xatol, xrtol,
                     fatol, frtol, maxiter, callback):

    if not callable(func):
        raise ValueError('`func` must be callable.')

    # a and b have more complex IV that is taken care of during initialization

    if not np.iterable(args):
        args = (args,)

    tols = np.asarray([xatol, xrtol, fatol if fatol is not None else 1, frtol])
    if (not np.issubdtype(tols.dtype, np.number)
            or np.any(tols < 0)
            or tols.shape != (4,)):
        raise ValueError('Tolerances must be non-negative scalars.')

    maxiter_int = int(maxiter)
    if maxiter != maxiter_int or maxiter < 0:
        raise ValueError('`maxiter` must be a non-negative integer.')

    if callback is not None and not callable(callback):
        raise ValueError('`callback` must be callable.')

    return func, a, b, args, xatol, xrtol, fatol, frtol, maxiter, callback


def _chandrupatla_initialize(func, xs, args):
    """Initializing abscissa and function arrays for elementwise function

    Parameters
    ----------
    func : callable
        An elementwise function with signature

            func(x: ndarray, *args) -> ndarray

        where each element of ``x`` is a finite real and ``args`` is a tuple,
        which may contain an arbitrary number of components of any type(s).
    xs : tuple of arrays
        Finite real abscissa arrays. Must be broadcastable.
    args : tuple, optional
        Additional positional arguments to be passed to `func`.

    Returns
    -------
    xs, fs : tuple of arrays
        Broadcasted, writeable, 1D abscissa and function value arrays (or
        NumPy floats, if appropriate) of the appropriate dtype.
    shape : tuple of ints
        Original shape of broadcasted arrays.
    xft : NumPy dtype
        Result dtype of abscissae and function values determined using
        `np.result_type`, except integer types are promoted to `np.float64`.

    Raises
    ------
    ValueError
        If the result dtype is not that of a real scalar

    Notes
    -----
    Useful for initializing the input of SciPy functions that accept
    an elementwise callable, abscissae, and arguments; e.g.
    `scipy.optimize._chandrupatla`.
    """

    # Try to preserve `dtype`, but we need to ensure that the arguments are at
    # least floats before passing them into the function because integers
    # can overflow and cause failure.
    # There might be benefit to combining the `xs` into a single array and
    # calling `func` once on the combined array. For now, keep them separate.
    xs = np.broadcast_arrays(*xs)  # broadcast and rename
    xt = np.result_type(*[x.dtype for x in xs])
    xt = np.float64 if np.issubdtype(xt, np.integer) else xt
    xs = [x.astype(xt, copy=False)[()] for x in xs]
    fs = [func(x, *args) for x in xs]

    # It's possible that the functions will return multiple outputs for each
    # scalar input, so we need to broadcast again. All arrays need to be,
    # writable, so we'll need to copy after broadcasting. Finally, we're going
    # to be doing operations involving `x1`, `x2`, `f1`, and `f2` throughout,
    # so figure out the right type from the outset.
    xfs = np.broadcast_arrays(*xs, *fs)
    xft = np.result_type(*[xf.dtype for xf in xfs])
    xft = np.float64 if np.issubdtype(xft, np.integer) else xft
    if not np.issubdtype(xft, np.floating):
        raise ValueError("Abscissae and function output must be real numbers.")
    xfs = [xf.astype(xt, copy=True)[()] for xf in xfs]
    xs, fs = xfs[:int(len(xfs)/2)], xfs[int(len(xfs)/2):]

    # To ensure that we can do indexing, we'll work with at least 1d arrays,
    # but remember the appropriate shape of the output.
    shape = xs[0].shape
    xs = [x.ravel() for x in xs]
    fs = [f.ravel() for f in fs]
    return xs, fs, shape, xft


def _chandrupatla_check_termination(work, res, active):
    # Check for all terminal conditions and record statuses.

    # See [1] Section 4 (first two sentences)
    i = np.abs(work.f1) < np.abs(work.f2)
    work.xmin = np.choose(i, (work.x2, work.x1))
    work.fmin = np.choose(i, (work.f2, work.f1))
    stop = np.zeros_like(work.x1, dtype=bool)  # termination condition met

    # This is the convergence criterion used in bisect. Chandrupatla's
    # criterion is equivalent to this except with a factor of 4 on `xrtol`.
    work.dx = abs(work.x2 - work.x1)
    work.tol = abs(work.xmin)*work.xrtol + work.xatol
    i = work.dx < work.tol
    # Modify in place to incorporate tolerance on function value. Note that
    # `frtol` has been redefined as `frtol = frtol * np.minimum(f1, f2)`,
    # where `f1` and `f2` are the function evaluated at the original ends of
    # the bracket.
    i |= np.abs(work.fmin) <= work.fatol + work.frtol
    work.status[i] = _ECONVERGED
    stop[i] = True

    i = (np.sign(work.f1) == np.sign(work.f2)) & ~stop
    work.xmin[i], work.fmin[i], work.status[i] = np.nan, np.nan, _ESIGNERR
    stop[i] = True

    i = ~((np.isfinite(work.x1) & np.isfinite(work.x2)
           & np.isfinite(work.f1) & np.isfinite(work.f2)) | stop)
    work.xmin[i], work.fmin[i], work.status[i] = np.nan, np.nan, _EVALUEERR
    stop[i] = True

    if np.any(stop):
        # update the active elements of the result object with the active
        # elements for which a termination condition has been met
        update_dict = dict(x=work.xmin, fun=work.fmin, xl=work.x1, xr=work.x2,
                           fl=work.f1, fr=work.f2, status=work.status,
                           nfev=work.nfev, nit=work.nit,
                           success=(work.status==0))
        _chandrupatla_update_active(res, update_dict, active, stop)

        # compress the arrays to avoid unnecessary computation
        proceed = ~stop
        active = active[proceed]
        _chandrupatla_compress_work(work, proceed)

    return work, active


def _chandrupatla_update_active(res, update_dict, active, mask=None):
    # Update `active` indices of the arrays in result upject `res` with the
    # contents of the scalars and arrays in `update_dict`. When provided,
    # `mask` is a boolean array applied both to the arrays in `update_dict`
    # that are to be used and to the arrays in `res` that are to be updated.
    if mask is not None:
        active_mask = active[mask]
        for key, val in update_dict.items():
            res[key][active_mask] = val[mask] if np.size(val) > 1 else val
    else:
        for key, val in update_dict.items():
            res[key][active] = val


def _chandrupatla_compress_work(work, mask):
    for key, val in work.items():
        work[key] = val[mask] if np.size(val) > 1 else val


def _chandrupatla_prepare_result(shape, res, active, work):
    res = res.copy()
    # status is _EINPROGRESS and success is False until set otherwise,
    # so these do not need to be updated
    update_dict = dict(x=work.xmin, fun=work.fmin, xl=work.x1, xr=work.x2,
                       fl=work.f1, fr=work.f2, nfev=work.nfev, nit=work.nit)
    _chandrupatla_update_active(res, update_dict, active)

    xl, xr, fl, fr = res['xl'], res['xr'], res['fl'], res['fr']
    i = res['xl'] < res['xr']
    res['xl'] = np.choose(i, (xr, xl))
    res['xr'] = np.choose(i, (xl, xr))
    res['fl'] = np.choose(i, (fr, fl))
    res['fr'] = np.choose(i, (fl, fr))
    for key, val in res.items():
        res[key] = np.reshape(val, shape)[()]
    res['_order_keys'] = ['success', 'status', 'x', 'fun', 'nit', 'nfev',
                          'xl', 'fl', 'xr', 'fr']
    return OptimizeResult(**res)
