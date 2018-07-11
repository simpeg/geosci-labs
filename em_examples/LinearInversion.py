import numpy as np
from SimPEG import Mesh
from SimPEG import Problem
from SimPEG import Survey
from SimPEG import DataMisfit
from SimPEG import Directives
from SimPEG import Optimization
from SimPEG import Regularization
from SimPEG import InvProblem
from SimPEG import Inversion
import matplotlib.pyplot as plt
from pymatsolver import Pardiso
import matplotlib
from ipywidgets import interact, FloatSlider, ToggleButtons, IntSlider, FloatText, IntText

class LinearInversionApp(object):
    """docstring for LinearInversionApp"""

    # Parameters for sensitivity matrix, G
    N=None
    M=None
    j_start=None
    j_end=None
    p=None
    q=None
    seed=None

    # Parameters for Model
    m_background= None
    m1=None
    m2=None
    m1_center=None
    dm1 =None
    m2_center=None
    dm2 =None
    sigma =None
    m_min =None
    m_max =None

    data=None
    save=None

    def __init__(self):
        super(LinearInversionApp, self).__init__()

    @property
    def G(self):
        return self._G

    @property
    def mesh(self):
        return self._mesh

    def set_G(
        self,
        N=20,
        M=100,
        p=-0.25,
        q=0.25,
    ):
        """
        Parameters
        ----------
        N: # of data
        M: # of model parameters
        ...

        """
        self.N=N
        self.M=M
        self._mesh=Mesh.TensorMesh([M])
        jk=np.arange(N)
        self._G=np.zeros((N, self.mesh.nC), dtype=float, order='C')

        def g(k):
            return (
                np.exp(p*jk[k]*self.mesh.vectorCCx) *
                np.cos(np.pi*q*jk[k]*self.mesh.vectorCCx)
            )

        for i in range(N):
            self._G[i, :]=g(i)

    def plot_G(
        self,
        N=20,
        M=100,
        p=-0.25,
        q=0.25,
        vmin=-0.1,
        vmax=1.1
    ):
        self.set_G(
            N=N,
            M=M,
            p=p,
            q=q,
        )
        matplotlib.rcParams['font.size']=14
        fig=plt.figure()
        plt.plot(self.mesh.vectorCCx, self.G.T)
        plt.ylim(vmin, vmax)
        plt.xlabel("x")
        plt.ylabel("g(x)")

    def set_model(
        self,
        m_background=0.,
        m1=1.,
        m2=-1.,
        m1_center=0.2,
        dm1=0.2,
        m2_center=0.5,
        sigma_2=1.,
    ):
        m=np.zeros(self.mesh.nC) + m_background
        m1_inds=np.logical_and(self.mesh.vectorCCx > m1_center-dm1/2., self.mesh.vectorCCx < m1_center+dm1/2.)
        m[m1_inds]=m1
        def gaussian(x,x0,sigma):
            return np.exp(-np.power((x - x0)/sigma, 2.)/2.)
        m += gaussian(self.mesh.vectorCCx, m2_center, sigma_2) * m2
        return m

    def plot_model(
        self,
        m_background=0.,
        m1=1.,
        m2=-1.,
        m1_center=0.2,
        dm1=0.2,
        m2_center=0.5,
        sigma_2=1.,
        option="model",
        add_noise=False,
        percentage =0.1,
        floor=1e-1,
        ):

        m=self.set_model(
            m_background=m_background,
            m1=m1,
            m2=m2,
            m1_center=m1_center,
            dm1=dm1,
            m2_center=m2_center,
            sigma_2=sigma_2,
        )

        if add_noise:
            survey, _=self.get_problem_survey()
            data=survey.dpred(m)
            noise=abs(data)*percentage*np.random.randn(self.N) + np.random.randn(self.N)*floor
        else:
            survey, _=self.get_problem_survey()
            data=survey.dpred(m)
            noise=np.zeros(self.N, float)

        data += noise
        self.data=data.copy()
        self.m=m.copy()
        self.uncertainty=abs(self.data) * percentage + floor
        self.percentage = percentage
        self.floor = floor

        if option == "model":
            fig, axes=plt.subplots(1, 1, figsize=(4*1.2, 3*1.2))
            axes.plot(self.mesh.vectorCCx, m)
            axes.set_ylim(-2.5, 2.5)
            axes.set_title('Model')
            axes.set_xlabel("x")
            axes.set_ylabel("m(x)")

        elif option == "data":
            fig, axes=plt.subplots(1, 2, figsize=(8*1.2, 3*1.2))
            axes[0].plot(self.mesh.vectorCCx, m)
            axes[0].set_ylim([-2.5, 2.5])
            if add_noise:
                axes[1].errorbar(
                    x=np.arange(self.N), y=self.data,
                    yerr=self.uncertainty,
                    color='k'
                )
            else:
                axes[1].plot(np.arange(self.N), self.data, 'k')
            axes[0].set_title('Model')
            axes[0].set_xlabel("x")
            axes[0].set_ylabel("m(x)")

            axes[1].set_title('Data')
            axes[1].set_xlabel("j")
            axes[1].set_ylabel("$d_j$")

        elif option == "kernel":
            fig, axes=plt.subplots(1, 3, figsize=(12*1.2, 3*1.2))
            axes[0].plot(self.mesh.vectorCCx, self.G.T)
            axes[0].set_title('Rows of matrix G')
            axes[0].set_xlabel("x")
            axes[0].set_ylabel("g(x)")
            axes[1].plot(self.mesh.vectorCCx, m)
            axes[1].set_ylim([-2.5, 2.5])
            if add_noise:
                # this is just for visualization of uncertainty
                visualization_factor=1.
                axes[2].errorbar(
                    x=np.arange(self.N), y=self.data,
                    yerr=self.uncertainty*visualization_factor,
                    color='k'
                )
            else:
                axes[2].plot(np.arange(self.N), self.data, 'k')

            axes[1].set_title('Model')
            axes[1].set_xlabel("x")
            axes[1].set_ylabel("m(x)")

            axes[2].set_title('Data')
            axes[2].set_xlabel("j")
            axes[1].set_ylabel("$d_j$")

        plt.tight_layout()


    def get_problem_survey(self):
        prob=Problem.LinearProblem(self.mesh, G=self.G, Solver=Pardiso)
        survey=Survey.LinearSurvey()
        survey.pair(prob)
        return survey, prob

    def run_inversion(
        self,
        maxIter=60,
        m0=0.,
        mref=0.,
        percentage=0.05,
        floor=0.1,
        rms=1,
        beta0_ratio=1.,
        coolingFactor=1,
        coolingRate=1,
        alpha_s=1.,
        alpha_x=1.,
    ):
        survey, prob=self.get_problem_survey()
        survey.eps=percentage
        survey.std=floor
        survey.dobs=self.data.copy()


        m0=np.ones(self.M) * m0
        mref=np.ones(self.M) * mref
        reg=Regularization.Tikhonov(
            self.mesh,
            alpha_s=alpha_s,
            alpha_x=alpha_x,
            mref=mref
        )
        dmis=DataMisfit.l2_DataMisfit(survey)
        dmis.W=1./self.uncertainty

        opt=Optimization.InexactGaussNewton(
            maxIter=maxIter,
            maxIterCG=20
        )
        opt.remember('xc')
        opt.tolG=1e-10
        opt.eps=1e-10
        invProb=InvProblem.BaseInvProblem(dmis, reg, opt)
        save=Directives.SaveOutputEveryIteration()
        beta_schedule=Directives.BetaSchedule(
            coolingFactor=coolingFactor,
            coolingRate=coolingRate
        )
        target=Directives.TargetMisfit(chifact=rms**2)
        directives=[
            Directives.BetaEstimate_ByEig(beta0_ratio=beta0_ratio),
            beta_schedule,
            target,
            save
        ]
        inv=Inversion.BaseInversion(invProb, directiveList=directives)
        mopt=inv.run(m0)
        model = opt.recall('xc')
        model.append(mopt)
        pred =  []
        for m in model:
            pred.append(survey.dpred(m))
        return model, pred, save

    def plot_inversion(
        self,
        maxIter=60,
        m0=0.,
        mref=0.,
        percentage=0.05,
        floor=0.1,
        rms=1,
        beta0_ratio=1.,
        coolingFactor=1,
        coolingRate=1,
        alpha_s=1.,
        alpha_x=1.,
        run=True,
        option ='model',
        i_iteration=1,
    ):

        if run:
            self.model, self.pred, self.save=self.run_inversion(
                maxIter=maxIter,
                m0=m0,
                mref=mref,
                percentage=percentage,
                floor=floor,
                rms=rms,
                beta0_ratio=beta0_ratio,
                coolingFactor=coolingFactor,
                coolingRate=coolingRate,
                alpha_s=alpha_s,
                alpha_x=alpha_x
            )

        self.save.load_results()
        fig, axes=plt.subplots(1, 3, figsize=(14*1.2, 3*1.2))
        axes[0].plot(self.mesh.vectorCCx, self.m)
        axes[0].plot(self.mesh.vectorCCx, self.model[-1])
        axes[0].set_ylim([-2.5, 2.5])
        axes[1].plot(np.arange(self.N), self.data, 'k')
        axes[1].plot(np.arange(self.N), self.pred[-1], 'bx')
        axes[1].legend(("Observed", "Predicted"))
        axes[0].legend(("True", "Pred"))
        # axes[1].errorbar(
        #     x=np.arange(self.N), y=self.data,
        #     yerr=self.uncertainty,
        #     color='k'
        # )
        axes[0].set_title('Model')
        axes[0].set_xlabel("x")
        axes[0].set_ylabel("m(x)")

        axes[1].set_title('Data')
        axes[1].set_xlabel("j")
        axes[1].set_ylabel("$d_j$")

        max_iteration = len(self.model)-1
        if i_iteration > max_iteration:
            print ((">> Warning: input iteration (%i) is greater than maximum iteration (%i)") % (i_iteration, len(self.model)-1))
            i_iteration = max_iteration

        if option == 'misfit':
            if not run:
                axes[0].plot(self.mesh.vectorCCx, self.model[i_iteration])
                axes[1].plot(np.arange(self.N), self.pred[i_iteration], 'g')
                axes[0].legend(("True", "Pred", ("%ith")%(i_iteration)))
                axes[1].legend(("Observed", "Predicted", ("%ith")%(i_iteration)))

                if i_iteration == 0:
                    i_iteration = 1
                axes[2].plot(np.arange(len(self.save.phi_d))[i_iteration-1]+1, self.save.phi_d[i_iteration-1], 'go', ms=10)


            ax_1 = axes[2].twinx()
            axes[2].semilogy(np.arange(len(self.save.phi_d))+1, self.save.phi_d, 'k-', lw=2)
            axes[2].plot(np.arange(len(self.save.phi_d))[self.save.i_target]+1, self.save.phi_d[self.save.i_target], 'k*', ms=10)
            ax_1.semilogy(np.arange(len(self.save.phi_d))+1, self.save.phi_m, 'r', lw=2)
            axes[2].plot(np.r_[axes[2].get_xlim()[0], axes[2].get_xlim()[1]], np.ones(2)*self.save.target_misfit, 'k:')
            axes[2].set_xlabel("Iteration")
            axes[2].set_ylabel("$\phi_d$")
            ax_1.set_ylabel("$\phi_m$", color='r')
            for tl in ax_1.get_yticklabels():
                tl.set_color('r')
            axes[2].set_title('Misfit curves')

        elif option == 'tikhonov':
            if not run:
                axes[0].plot(self.mesh.vectorCCx, self.model[i_iteration])
                axes[1].plot(np.arange(self.N), self.pred[i_iteration], 'g')
                axes[0].legend(("True", "Pred", ("%ith")%(i_iteration)))
                axes[1].legend(("Observed", "Predicted", ("%ith")%(i_iteration)))
                if i_iteration == 0:
                    i_iteration = 1
                axes[2].plot(self.save.phi_m[i_iteration-1], self.save.phi_d[i_iteration-1], 'go', ms=10)

            axes[2].plot(self.save.phi_m, self.save.phi_d, 'k-', lw=2)
            axes[2].set_xlim(np.hstack(self.save.phi_m).min(), np.hstack(self.save.phi_m).max())
            axes[2].set_xlabel("$\phi_m$", fontsize=14)
            axes[2].set_ylabel("$\phi_d$", fontsize=14)
            axes[2].plot(self.save.phi_m[self.save.i_target], self.save.phi_d[self.save.i_target], 'k*', ms=10)
            axes[2].set_title('Tikhonov curve')

        plt.tight_layout()


    def interact_plot_G(self):
        Q=interact(
            self.plot_G,
            N=IntSlider(min=1, max=100, step=1, value=20, continuous_update=False),
            M=IntSlider(min=1, max=100, step=1, value=100, continuous_update=False),
            p =FloatSlider(min=-1, max=0, step=0.05, value=-0.5, continuous_update=False),
            q=FloatSlider(min=0, max=1, step=0.05, value=0.5, continuous_update=False),
            vmin=FloatText(value=-0.5),
            vmax=FloatText(value=1.1)
        )
        return Q

    def interact_plot_model(self):
        Q=interact(
            self.plot_model,
            m_background=FloatSlider(
                min=-2, max=2, step=0.05, value=0., continuous_update=False
            ),
            m1=FloatSlider(
                min=-2, max=2, step=0.05, value=1., continuous_update=False
            ),
            m2=FloatSlider(
                min=-2, max=2, step=0.05, value=2., continuous_update=False
            ),
            m1_center=FloatSlider(
                min=-2, max=2, step=0.05, value=0.2, continuous_update=False
            ),
            dm1 =FloatSlider(
                min=0, max=0.5, step=0.05, value=0.2, continuous_update=False
            ),
            m2_center=FloatSlider(
                min=-2, max=2, step=0.05, value=0.75, continuous_update=False
            ),
            sigma_2=FloatSlider(
                min=0.01, max=0.1, step=0.01, value=0.07, continuous_update=False
            ),
            option=ToggleButtons(
                options=["model", "data", "kernel"], value="model"
            ),
            percentage=FloatText(value=0.1),
            floor=FloatText(value=0.1),
        )
        return Q

    def interact_plot_inversion(self):
        maxIter = 20
        Q = interact(
            self.plot_inversion,
                maxIter=IntText(value=20),
                m0=FloatSlider(min=-2, max=2, step=0.05, value=0., continuous_update=False),
                mref=FloatSlider(min=-2, max=2, step=0.05, value=0., continuous_update=False),
                percentage=FloatSlider(min=0, max=1, step=0.01, value=self.percentage, continuous_update=False),
                floor=FloatSlider(min=0, max=1, step=0.01, value=self.floor, continuous_update=False),
                rms=FloatSlider(min=0.01, max=10, step=0.01, value=1., continuous_update=False),
                beta0_ratio=FloatText(value=100),
                coolingFactor=FloatSlider(min=0.1, max=10, step=1, value=2, continuous_update=False),
                coolingRate=IntSlider(min=1, max=10, step=1, value=1, continuous_update=False),
                alpha_s=FloatText(value=1),
                alpha_x=FloatText(value=1),
                run = True,
                option=ToggleButtons(
                    options=["misfit", "tikhonov"], value="misfit"
                ),
                i_iteration=IntSlider(min=0, max=maxIter, step=1, value=0, continuous_update=False)
        )
